import QtQuick
import Quickshell
import Quickshell.Io

// Quickshell exposes QProcess signal parameters that qmllint cannot resolve.
// qmllint disable signal-handler-parameters

QtObject {
  id: root

  property var shell: null
  property var manifest: null

  property bool available: false
  property bool terminating: false
  readonly property bool busy: commandProcess.running || terminating || currentKind !== ""
  property int version: 0
  property string mode: "dynamic"
  property string configuredStaticColor: "#FFFFFF"
  property int configuredBrightness: -1
  property bool colorMatching: false
  property string requestedColor: ""
  property string requestedSource: ""
  property string appliedColor: ""
  property int appliedBrightness: -1
  property string connection: "starting"
  property string message: ""
  property double updatedAt: 0
  property string actionMessage: ""
  property string error: ""

  property var queuedAction: null
  property bool queuedSync: false
  property bool queuedStatus: false
  property string currentKind: ""
  property bool timedOut: false

  readonly property string executable: (Quickshell.env("HOME") || "") + "/.local/bin/edifier-qr65"
  readonly property int statusHeartbeatMaxAgeSec: 15
  readonly property bool fallbackActive: mode === "dynamic"
    && requestedSource === "static-fallback"
  readonly property bool connected: available && connection === "connected"

  function validColor(value, allowEmpty) {
    var text = value === null || value === undefined ? "" : String(value)
    return (allowEmpty && text === "") || /^#[0-9A-Fa-f]{6}$/.test(text)
  }

  function boundedDiagnostic(value, fallback) {
    var text = String(value || "").trim()
    if (text.length > 512) text = text.slice(0, 509) + "..."
    return text || fallback
  }

  function setUnavailable(reason) {
    available = false
    connection = "error"
    requestedColor = ""
    requestedSource = ""
    appliedColor = ""
    appliedBrightness = -1
    configuredBrightness = -1
    message = ""
    updatedAt = 0
    error = boundedDiagnostic(reason, "QR65 status is unavailable.")
  }

  function statusIsStale(timestamp) {
    return timestamp <= 0 || Date.now() / 1000 - timestamp > statusHeartbeatMaxAgeSec
  }

  function enforceStatusAge() {
    if (available && connection === "connected" && statusIsStale(updatedAt))
      setUnavailable("QR65 connected status is stale (over 15 seconds old).")
  }

  function applyStatus(raw) {
    var text = String(raw || "")
    if (text.length === 0 || text.length > 65536) {
      setUnavailable(text.length > 65536 ? "QR65 status exceeded 64 KiB." : "QR65 returned no status.")
      return false
    }

    var status
    try { status = JSON.parse(text) } catch (parseError) {
      setUnavailable("QR65 returned malformed JSON.")
      return false
    }
    var connections = ["starting", "scanning", "activation-required", "connecting", "connected", "released", "error"]
    if (!status || Array.isArray(status) || typeof status !== "object"
        || status.version !== 1
        || (status.mode !== "dynamic" && status.mode !== "static")
        || !validColor(status.configuredStaticColor, false)
        || !(status.configuredBrightness === undefined
          || status.configuredBrightness === null
          || (typeof status.configuredBrightness === "number"
            && isFinite(status.configuredBrightness)
            && Math.floor(status.configuredBrightness) === status.configuredBrightness
            && status.configuredBrightness >= 0 && status.configuredBrightness <= 100))
        || !(status.colorMatching === undefined || typeof status.colorMatching === "boolean")
        || !validColor(status.requestedColor, true)
        || !validColor(status.appliedColor, true)
        || !(status.appliedBrightness === undefined
          || status.appliedBrightness === null
          || (typeof status.appliedBrightness === "number"
            && isFinite(status.appliedBrightness)
            && Math.floor(status.appliedBrightness) === status.appliedBrightness
            && status.appliedBrightness >= 0 && status.appliedBrightness <= 100))
        || typeof status.requestedSource !== "string" || status.requestedSource.length > 128
        || connections.indexOf(status.connection) < 0
        || typeof status.message !== "string" || status.message.length > 2048
        || typeof status.updatedAt !== "number" || !isFinite(status.updatedAt)) {
      setUnavailable("QR65 returned an unsupported status payload.")
      return false
    }
    if (status.connection === "connected" && statusIsStale(status.updatedAt)) {
      setUnavailable("QR65 connected status is stale (over 15 seconds old).")
      return false
    }

    version = status.version
    mode = status.mode
    configuredStaticColor = status.configuredStaticColor.toUpperCase()
    configuredBrightness = status.configuredBrightness === undefined
      || status.configuredBrightness === null ? -1 : status.configuredBrightness
    colorMatching = status.colorMatching === undefined ? false : status.colorMatching
    requestedColor = String(status.requestedColor || "").toUpperCase()
    requestedSource = status.requestedSource
    appliedColor = String(status.appliedColor || "").toUpperCase()
    appliedBrightness = status.appliedBrightness === undefined
      || status.appliedBrightness === null ? -1 : status.appliedBrightness
    connection = status.connection
    message = status.message
    updatedAt = status.updatedAt
    available = true
    error = ""
    return true
  }

  function launch(kind, args) {
    if (busy || executable === "") return false
    currentKind = kind
    timedOut = false
    commandProcess.command = [executable].concat(args)
    timeoutTimer.restart()
    commandProcess.running = true
    return true
  }

  function refresh() {
    if (busy) {
      queuedStatus = true
      return
    }
    launch("status", ["status", "--json"])
  }

  function setDynamic() {
    var action = { kind: "dynamic", args: ["mode", "dynamic"] }
    if (busy) {
      queuedAction = action
      queuedSync = false
    }
    else launch(action.kind, action.args)
    return true
  }

  function setStatic(color) {
    var normalized = String(color || "").toUpperCase()
    if (!validColor(normalized, false)) {
      actionMessage = "Enter a color as #RRGGBB."
      actionMessageTimer.restart()
      return false
    }
    var action = { kind: "static", args: ["mode", "static", normalized] }
    if (busy) {
      queuedAction = action
      queuedSync = false
    }
    else launch(action.kind, action.args)
    return true
  }

  function sync() {
    if (busy) queuedSync = true
    else launch("sync", ["sync"])
    return true
  }

  function setBrightness(value) {
    var percent = Math.max(0, Math.min(100, Math.round(Number(value))))
    var action = { kind: "brightness", args: ["brightness", String(percent)] }
    configuredBrightness = percent
    if (busy) {
      queuedAction = action
      queuedSync = false
    } else launch(action.kind, action.args)
    return true
  }

  function setColorMatching(enabled) {
    var value = !!enabled
    var action = { kind: "matching", args: ["color-matching", value ? "on" : "off"] }
    colorMatching = value
    if (busy) {
      queuedAction = action
      queuedSync = false
    } else launch(action.kind, action.args)
    return true
  }

  function releaseToApp() {
    var action = { kind: "release", args: ["release"] }
    if (busy) {
      queuedAction = action
      queuedSync = false
    } else launch(action.kind, action.args)
    return true
  }

  function resumeDaemon() {
    var action = { kind: "resume", args: ["resume"] }
    if (busy) {
      queuedAction = action
      queuedSync = false
    } else launch(action.kind, action.args)
    return true
  }

  function statusJson() {
    return JSON.stringify({
      available: available, version: version, mode: mode,
      configuredStaticColor: configuredStaticColor,
      configuredBrightness: configuredBrightness, colorMatching: colorMatching,
      requestedColor: requestedColor, requestedSource: requestedSource,
      appliedColor: appliedColor, appliedBrightness: appliedBrightness, connection: connection,
      message: message, updatedAt: updatedAt, busy: busy, error: error
    })
  }

  function drainQueue() {
    if (busy) return
    if (queuedAction) {
      var action = queuedAction
      queuedAction = null
      launch(action.kind, action.args)
    } else if (queuedSync) {
      queuedSync = false
      launch("sync", ["sync"])
    } else if (queuedStatus) {
      queuedStatus = false
      launch("status", ["status", "--json"])
    }
  }

  Component.onCompleted: refresh()

  property Timer pollTimer: Timer {
    interval: 8000
    repeat: true
    running: true
    onTriggered: root.refresh()
  }

  property Timer statusAgeTimer: Timer {
    interval: 1000
    repeat: true
    running: true
    onTriggered: root.enforceStatusAge()
  }

  property Timer timeoutTimer: Timer {
    interval: 20000
    onTriggered: {
      root.timedOut = true
      root.terminating = true
      root.queuedStatus = true
      root.setUnavailable("QR65 command timed out.")
      if (root.commandProcess.running) root.commandProcess.running = false
    }
  }

  property Timer actionMessageTimer: Timer {
    interval: 3000
    onTriggered: root.actionMessage = ""
  }

  property Process commandProcess: Process {
    running: false
    command: []
    stdout: StdioCollector { id: commandOut; waitForEnd: true }
    stderr: StdioCollector { id: commandErr; waitForEnd: true }

    onExited: function(exitCode) {
      root.timeoutTimer.stop()
      var kind = root.currentKind
      root.currentKind = ""
      if (!root.timedOut) {
        if (kind === "status") {
          if (exitCode === 0) root.applyStatus(commandOut.text)
          else root.setUnavailable(root.boundedDiagnostic(commandErr.text, "QR65 status command failed."))
        } else {
          if (exitCode === 0) {
            root.actionMessage = kind === "dynamic" ? "Following theme colors."
              : kind === "static" ? "Static color selected."
              : kind === "brightness" ? "Brightness updated."
              : kind === "matching" ? "Screen matching updated." : "Color reapplied."
            if (kind === "release") root.actionMessage = "BLE released to ConneX."
            else if (kind === "resume") root.actionMessage = "QR65 daemon resumed."
            root.error = ""
          } else {
            root.actionMessage = root.boundedDiagnostic(commandErr.text, "QR65 command failed.")
          }
          root.actionMessageTimer.restart()
          root.queuedStatus = true
        }
      }
      root.timedOut = false
      root.terminating = false
      Qt.callLater(root.drainQueue)
    }
  }
}
