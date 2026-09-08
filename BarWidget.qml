pragma ComponentBehavior: Bound

import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.BarWidget {
  id: root
  moduleName: "lightqv.edifier-qr65"

  readonly property var service: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
  readonly property var panelAnchor: button
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item
    ? panelLoader.item.popoutSwitchClosing === true : false

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    target.bar = root.bar
    target.settings = root.settings
    target.anchorItem = button
    target.hostWidget = root
    target.service = root.service
  }

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function togglePanel() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()
  onServiceChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  Ui.BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    keepSpace: true
    dimmed: !root.service || !root.service.available
      || ["starting", "scanning", "connecting", "activation-required", "released"].indexOf(root.service.connection) >= 0
    active: root.service && (root.service.connection === "error"
      || root.service.connection === "activation-required" || root.service.fallbackActive)
    iconComponent: Component {
      Qr65Icon {
        glyphSize: button.fontSize
        fontFamily: button.fontFamily
        foreground: button.active && button.useActiveColor ? button.activeColor : button.foreground
        indicatorColor: root.service && root.service.validColor(root.service.requestedColor, false)
          ? root.service.requestedColor : "transparent"
        showIndicator: true
      }
    }
    tooltipText: {
      if (!root.service) return "QR65 service unavailable"
      var lines = ["Edifier QR65",
        "Mode: " + (root.service.mode === "dynamic" ? "Follow Theme" : "Static Color")]
      lines.push("Screen matching: " + (root.service.colorMatching ? "On" : "Off"))
      if (root.service.appliedBrightness >= 0)
        lines.push("Brightness: " + root.service.appliedBrightness + "%")
      if (root.service.connection === "starting") lines.push("Starting QR65 control...")
      if (root.service.connection === "scanning") lines.push("Searching for the QR65...")
      if (root.service.connection === "connecting") lines.push("Connecting to the QR65...")
      if (root.service.connection === "activation-required")
        lines.push("Switch to Bluetooth input and let the paired phone connect.")
      if (root.service.connection === "released")
        lines.push("Control released to ConneX.")
      if (root.service.connection === "error")
        lines.push(root.service.error || root.service.message || "QR65 control unavailable.")
      return lines.join("\n")
    }
    Accessible.role: Accessible.Button
    Accessible.name: tooltipText
    Accessible.onPressAction: root.togglePanel()
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.LeftButton) root.togglePanel()
    }
  }
}
