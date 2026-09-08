pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Ui.Panel {
  id: root
  moduleName: "lightqv.edifier-qr65"

  property var shell: null
  property var manifest: null
  property var service: null
  property var anchorItem: null
  property var hostWidget: null
  property int section: 0
  property int modeIndex: 0
  property int paletteIndex: 0
  property int editorIndex: 0
  property string draftColor: service && service.configuredStaticColor
    ? service.configuredStaticColor : "#FFFFFF"

  readonly property var svc: service || (shell && typeof shell.serviceFor === "function"
    ? shell.serviceFor(moduleName) : null)
  readonly property var colorPresets: ["#FFFFFF", "#FFB86C", "#FF5555", "#FF79C6",
    "#BD93F9", "#89B4FA", "#8BE9FD", "#50FA7B"]
  readonly property bool validDraft: /^#[0-9A-Fa-f]{6}$/.test(draftColor)
  readonly property var barIdentity: hostWidget || root
  readonly property color foreground: bar ? bar.barForeground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property int brightnessValue: svc
    ? (svc.configuredBrightness >= 0 ? svc.configuredBrightness
      : Math.max(0, svc.appliedBrightness)) : 0

  function resolveHost() {
    if (!bar && shell && shell.bar) bar = shell.bar
    if (!hostWidget && bar && typeof bar.moduleWidgets === "function") {
      var widgets = bar.moduleWidgets(moduleName)
      if (widgets.length > 0) hostWidget = widgets[0]
    }
    if (!anchorItem && hostWidget && hostWidget.panelAnchor) anchorItem = hostWidget.panelAnchor
  }

  function open() {
    resolveHost()
    controller.show()
    if (svc) svc.refresh()
  }
  function close() {
    controller.hide()
  }
  function toggle() { opened ? close() : open() }
  function switchPanel(direction) {
    return bar && typeof bar.switchPanelFrom === "function"
      ? bar.switchPanelFrom(barIdentity, direction) : false
  }

  function move(dx, dy) {
    if (section === 0) {
      if (dy > 0) section = 1
    }
    else if (section === 1) {
      if (dx !== 0) modeIndex = Math.max(0, Math.min(1, modeIndex + dx))
      else if (dy < 0) section = 0
      else if (dy > 0) section = svc && svc.mode === "static" ? 2 : 4
    }
    else if (section === 2) {
      var step = dx !== 0 ? dx : dy * 4
      var next = paletteIndex + step
      if (next >= 0 && next < colorPresets.length) paletteIndex = next
      else if (dy < 0) section = 1
      else if (dy > 0) section = 3
    } else if (section === 3) {
      if (dx !== 0) editorIndex = Math.max(0, Math.min(1, editorIndex + dx))
      else if (dy < 0) section = 2
      else if (dy > 0) section = 4
    } else if (section === 4) {
      if (dx !== 0 && svc && svc.connected && !svc.busy)
        svc.setBrightness(brightnessValue + dx)
      else if (dy < 0) section = svc && svc.mode === "static" ? 3 : 1
      else if (dy > 0) section = 5
    } else if (section === 5) {
      if (dy < 0) section = 4
      else if (dy > 0) section = 6
    } else {
      if (dy < 0) section = 5
    }
    Qt.callLater(ensureCursorVisible)
  }

  function ensureCursorVisible() {
    var target = section === 0 ? header : section === 1 ? modeSection
      : section === 2 ? paletteGrid : section === 3 ? editorRow
      : section === 4 ? brightnessSection : section === 5 ? matchingSection : footerSection
    var top = target.mapToItem(content, 0, 0).y
    var bottom = top + target.height
    if (top < panelFlick.contentY) panelFlick.contentY = top
    else if (bottom > panelFlick.contentY + panelFlick.height)
      panelFlick.contentY = Math.max(0, Math.min(bottom - panelFlick.height,
        panelFlick.contentHeight - panelFlick.height))
  }

  function activate() {
    if (!svc) return
    if (section === 0) {
      if (svc.busy) return
      svc.connection === "released" ? svc.resumeDaemon() : svc.releaseToApp()
    } else if (section === 1) {
      if (modeIndex === 0) svc.setDynamic()
      else svc.setStatic(svc.configuredStaticColor)
    } else if (section === 2) {
      draftColor = colorPresets[paletteIndex]
      svc.setStatic(draftColor)
    } else if (section === 3) {
      if (editorIndex === 0) hexField.forceActiveFocus()
      else if (validDraft) svc.setStatic(draftColor)
    } else if (section === 5) {
      if (svc.busy) return
      svc.setColorMatching(!svc.colorMatching)
    } else if (section === 6 && svc.connection !== "released") svc.sync()
  }

  function choosePalette(index) {
    section = 2
    paletteIndex = index
    draftColor = colorPresets[index]
    hexField.text = draftColor
    if (svc) svc.setStatic(draftColor)
  }

  function connectionLabel(value) {
    if (value === "activation-required") return "Activation required"
    if (value === "released") return "Released to ConneX"
    return String(value || "unavailable").replace(/-/g, " ")
  }

  Component.onCompleted: resolveHost()
  onShellChanged: resolveHost()
  onOpenedChanged: if (opened) {
    panelFlick.contentY = 0
    section = 0
    modeIndex = svc && svc.mode === "static" ? 1 : 0
    if (svc) {
      draftColor = svc.configuredStaticColor
      hexField.text = draftColor
      svc.refresh()
    }
    Qt.callLater(keyCatcher.forceActiveFocus)
  }

  Connections {
    target: root.svc
    function onModeChanged() {
      root.modeIndex = root.svc && root.svc.mode === "static" ? 1 : 0
      if (root.svc && root.svc.mode !== "static"
          && (root.section === 2 || root.section === 3)) {
        root.section = 1
        Qt.callLater(root.ensureCursorVisible)
      }
    }
  }

  Ui.KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(content.implicitHeight, Style.space(560))

    Ui.PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: hexField.activeFocus
      onMoveRequested: function(dx, dy) { root.move(dx, dy) }
      onActivateRequested: root.activate()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(text) {
        if (text === "/" && root.svc && root.svc.mode === "static") {
          root.section = 3
          root.editorIndex = 0
          root.ensureCursorVisible()
          Qt.callLater(hexField.forceActiveFocus)
        }
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
          id: content
          width: parent.width
          spacing: Style.space(12)

          Item {
            id: header
            width: parent.width
            implicitHeight: hero.implicitHeight
            readonly property var panelService: root.svc
            readonly property color panelForeground: root.foreground

            Ui.PanelHero {
              id: hero
              width: parent.width
              title: root.manifest && root.manifest.name ? root.manifest.name : "Edifier QR65"
              meta: root.connectionLabel(root.svc ? root.svc.connection : "unavailable")
              foreground: root.foreground
              fontFamily: root.fontFamily
              iconOpacity: root.svc && root.svc.connected ? 1.0 : 0.5
              iconComponent: Component {
                Qr65Icon {
                  glyphSize: hero.iconSize
                  fontFamily: root.fontFamily
                  foreground: header.panelForeground
                  showIndicator: false
                }
              }
              trailingControl: Component {
                Ui.ToggleSwitch {
                  id: ownershipSwitch
                  checked: header.panelService && header.panelService.connection !== "released"
                  busy: header.panelService && header.panelService.busy
                  hasCursor: root.section === 0
                  foreground: header.panelForeground
                  onHovered: function(value) { if (value) root.section = 0 }
                  onToggled: if (header.panelService) checked
                    ? header.panelService.releaseToApp() : header.panelService.resumeDaemon()
                  Ui.PanelToolTip {
                    visible: ownershipSwitch.containsMouse
                    text: ownershipSwitch.checked ? "Release to ConneX" : "Resume QR65 control"
                    fontFamily: root.fontFamily
                  }
                }
              }
            }
          }

          Ui.PanelSeparator { foreground: root.foreground }

          Text {
            width: parent.width
            visible: root.svc && root.svc.connection === "activation-required"
            text: "Switch the QR65 to Bluetooth input. Let the paired phone connect with ConneX closed; after Linux connects, switch back to wired input."
            color: root.urgent; font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap; textFormat: Text.PlainText
          }
          Text {
            width: parent.width
            visible: root.svc && root.svc.connection !== "activation-required"
              && root.svc.connection !== "released"
              && (root.svc.message !== "" || root.svc.error !== "")
            text: root.svc ? (root.svc.error || root.svc.message) : ""
            color: root.svc && root.svc.error !== "" ? root.urgent : Qt.darker(root.foreground, 1.3)
            font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap; textFormat: Text.PlainText
          }
          Text {
            width: parent.width
            visible: root.svc && root.svc.connection === "released"
            text: "BLE is available to ConneX. Connect the phone to QR65 Bluetooth audio before opening the app. Close ConneX before resuming."
            color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap; textFormat: Text.PlainText
          }

          Column {
            id: modeSection
            width: parent.width
            spacing: Style.space(10)
            Ui.PanelSectionHeader { text: "MODE"; foreground: root.foreground; fontFamily: root.fontFamily }
            Row {
              width: parent.width
              spacing: Style.space(8)
              Repeater {
                model: ["Follow Theme", "Static Color"]
                delegate: Ui.Button {
                  required property int index
                  required property string modelData
                  width: (content.width - Style.space(8)) / 2
                  text: modelData
                  foreground: root.foreground
                  selected: root.svc && root.svc.mode === (index === 0 ? "dynamic" : "static")
                  hasCursor: root.section === 1 && root.modeIndex === index
                  Accessible.role: Accessible.Button
                  Accessible.name: modelData
                  Accessible.onPressAction: clicked()
                  onHovered: function(value) { if (value) { root.section = 1; root.modeIndex = index } }
                  onClicked: {
                    root.section = 1; root.modeIndex = index
                    if (root.svc) index === 0 ? root.svc.setDynamic() : root.svc.setStatic(root.svc.configuredStaticColor)
                  }
                }
              }
            }
            Text {
              width: parent.width
              visible: root.svc && root.svc.fallbackActive
              text: "Theme color unavailable; using the saved static color until it becomes available."
              color: root.urgent; font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap; textFormat: Text.PlainText
            }
          }

          Ui.PanelSeparator {
            foreground: root.foreground
            visible: root.svc && root.svc.mode === "static"
          }

          Column {
            id: staticSection
            width: parent.width
            spacing: Style.space(10)
            visible: root.svc && root.svc.mode === "static"
            Ui.PanelSectionHeader { text: "STATIC COLOR"; foreground: root.foreground; fontFamily: root.fontFamily }
            Grid {
              id: paletteGrid
              width: parent.width
              columns: 4
              spacing: Style.space(8)
              Repeater {
                model: root.colorPresets
                delegate: Ui.CursorSurface {
                  id: swatch
                  required property int index
                  required property string modelData
                  width: (content.width - Style.space(24)) / 4
                  height: Style.space(34)
                   hasCursor: root.section === 2 && root.paletteIndex === index
                  current: root.svc && root.svc.mode === "static"
                    && root.svc.configuredStaticColor.toUpperCase() === modelData
                  Accessible.role: Accessible.Button
                  Accessible.name: "Set static color " + modelData
                  Accessible.onPressAction: root.choosePalette(index)
                  Rectangle {
                    anchors.centerIn: parent
                    width: Style.space(20); height: width; radius: width / 2
                    color: swatch.modelData; border.width: 1; border.color: root.foreground
                  }
                  MouseArea {
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                     onEntered: { root.section = 2; root.paletteIndex = swatch.index }
                    onClicked: root.choosePalette(swatch.index)
                  }
                }
              }
            }

            RowLayout {
              id: editorRow
              width: parent.width
              spacing: Style.space(8)
              Rectangle {
                Layout.preferredWidth: Style.space(28)
                Layout.preferredHeight: Style.space(28)
                radius: Style.space(14)
                color: root.validDraft ? root.draftColor : "transparent"
                border.width: 1; border.color: root.validDraft ? root.foreground : root.urgent
              }
              Ui.TextField {
                id: hexField
                Layout.fillWidth: true
                text: root.draftColor
                placeholderText: "#RRGGBB"
                foreground: root.validDraft ? root.foreground : root.urgent
                 hasCursor: root.section === 3 && root.editorIndex === 0
                validator: RegularExpressionValidator { regularExpression: /^#[0-9A-Fa-f]{6}$/ }
                Accessible.name: "Static hexadecimal color"
                onTextEdited: root.draftColor = text.toUpperCase()
                Keys.onPressed: function(event) {
                  if (event.key === Qt.Key_Escape) {
                    keyCatcher.forceActiveFocus(); event.accepted = true
                  } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && root.validDraft) {
                    if (root.svc) root.svc.setStatic(root.draftColor)
                    keyCatcher.forceActiveFocus(); event.accepted = true
                  }
                }
              }
              Ui.Button {
                text: "Apply"
                enabled: root.validDraft && !!root.svc
                foreground: root.foreground
                 hasCursor: root.section === 3 && root.editorIndex === 1
                Accessible.role: Accessible.Button
                Accessible.name: "Apply static color"
                Accessible.onPressAction: clicked()
                 onHovered: function(value) { if (value) { root.section = 3; root.editorIndex = 1 } }
                onClicked: if (root.svc) root.svc.setStatic(root.draftColor)
              }
            }
          }

          Ui.PanelSeparator { foreground: root.foreground }

          Column {
            id: brightnessSection
            width: parent.width
            spacing: Style.space(6)

            Item {
              width: parent.width
              implicitHeight: Math.max(brightnessHeader.implicitHeight, brightnessPercent.implicitHeight)
              Ui.PanelSectionHeader {
                id: brightnessHeader
                text: "BRIGHTNESS"
                foreground: root.foreground
                fontFamily: root.fontFamily
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
              }
              Text {
                id: brightnessPercent
                text: Math.round(brightnessSlider.dragging
                  ? brightnessSlider.liveValue : root.brightnessValue) + "%"
                color: Qt.darker(root.foreground, 1.4)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
                anchors.right: parent.right
                anchors.rightMargin: Style.space(6)
                anchors.verticalCenter: parent.verticalCenter
                opacity: brightnessSlider.enabled ? 1.0 : 0.5
              }
            }

            Ui.CursorSurface {
              id: brightnessRow
              width: parent.width
              height: brightnessSlider.implicitHeight + Style.spacing.controlGap
              hasCursor: root.section === 4
              foreground: root.foreground
              outline: true
              Ui.PanelSlider {
                id: brightnessSlider
                bar: root.bar
                anchors.fill: parent
                anchors.leftMargin: Style.space(6)
                anchors.rightMargin: Style.space(6)
                minimum: 0
                maximum: 100
                step: 1
                integer: true
                value: root.brightnessValue
                enabled: root.svc && root.svc.connected && !root.svc.busy
                onReleased: function(value) { if (root.svc) root.svc.setBrightness(value) }
              }
              HoverHandler { onHoveredChanged: if (hovered) root.section = 4 }
            }
          }

          Ui.PanelSeparator { foreground: root.foreground }

          Item {
            id: matchingSection
            width: parent.width
            implicitHeight: Math.max(matchingHeader.implicitHeight, matchingSwitch.implicitHeight)
            Ui.PanelSectionHeader {
              id: matchingHeader
              text: "MATCH SCREEN COLORS"
              foreground: root.foreground
              fontFamily: root.fontFamily
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
            }
            Ui.ToggleSwitch {
              id: matchingSwitch
              checked: root.svc && root.svc.colorMatching
              busy: root.svc && root.svc.busy
              hasCursor: root.section === 5
              foreground: root.foreground
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              onHovered: function(value) { if (value) root.section = 5 }
              onToggled: if (root.svc) root.svc.setColorMatching(!checked)
              Ui.PanelToolTip {
                visible: matchingSwitch.containsMouse
                text: matchingSwitch.checked ? "Use literal RGB"
                  : "Use profile calibrated at 50% brightness"
                fontFamily: root.fontFamily
              }
            }
          }

          Ui.PanelSeparator { foreground: root.foreground }

          Column {
            id: footerSection
            width: parent.width
            spacing: Style.space(8)
            Ui.Button {
              width: parent.width
              text: "Reapply Color"
              iconText: "󰑓"
              foreground: root.foreground
              hasCursor: root.section === 6
              enabled: !!root.svc && root.svc.connection !== "released"
              Accessible.role: Accessible.Button
              Accessible.name: "Reapply current QR65 color"
              Accessible.onPressAction: clicked()
              onHovered: function(value) { if (value) root.section = 6 }
              onClicked: if (root.svc) root.svc.sync()
            }
            Text {
              width: parent.width
              text: root.svc && root.svc.actionMessage !== "" ? root.svc.actionMessage
                : "Arrows/hjkl move  ·  Enter/Space select  ·  Tab changes panel  ·  Esc closes"
              color: Qt.darker(root.foreground, 1.4)
              font.family: root.fontFamily; font.pixelSize: Style.font.caption
              horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
              textFormat: Text.PlainText
            }
          }
        }
      }
    }
  }
}
