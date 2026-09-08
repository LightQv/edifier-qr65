import QtQuick
import qs.Commons
import qs.Ui as Ui

Item {
  id: root

  property real glyphSize: Style.font.icon
  property string fontFamily: Style.font.family
  property color foreground: Color.foreground
  property color indicatorColor: "transparent"
  property bool showIndicator: false

  implicitWidth: glyphSize
  implicitHeight: glyphSize

  Ui.OpticalGlyph {
    anchors.fill: parent
    text: "󰌵"
    fontFamily: root.fontFamily
    fontSize: root.glyphSize
    color: root.foreground
  }

  Rectangle {
    width: Math.max(Style.space(6), Math.round(root.glyphSize * 0.38))
    height: width
    radius: width / 2
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    color: root.indicatorColor
    border.width: 1
    border.color: Color.popups.background
    visible: root.showIndicator && color.a > 0
  }
}
