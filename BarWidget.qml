import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "ochessy"

  readonly property var status: panelLoader.item ? panelLoader.item.status : Model.defaultStatus()
  readonly property string tooltipLabel: Model.barTooltip(status)
  readonly property string pillText: Model.barLabel(status)
  // Rating move since the previous game in the same pool. The number alone
  // says where you are; this says which way you are going, which is the part
  // worth a glance from across the desk.
  readonly property string deltaText: Model.deltaLabel(status)
  readonly property int ratingDelta: Model.ratingDelta(status)
  readonly property color chipFill: root.ratingDelta < 0 ? Color.urgent : Color.accent
  readonly property color chipInk: Color.bar.text
  readonly property int chipH: Math.max(22, root.barSize - 8)
  readonly property int chipW: Math.max(48, Math.round(chipH * 2.15) + (root.deltaText === "" ? 0 : 24))

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  function refresh() {
    if (panelLoader.item && panelLoader.item.refresh) panelLoader.item.refresh()
  }

  function reviewLast() {
    if (panelLoader.item && panelLoader.item.reviewLast) panelLoader.item.reviewLast()
  }

  function persistSettings(values) {
    var entry = { id: root.moduleName }
    for (var existing in root.settings) if (existing !== "id") entry[existing] = root.settings[existing]
    for (var key in values) entry[key] = values[key]
    root.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function togglePanel() {
    if (panelLoader.item) panelLoader.item.toggle()
  }

  readonly property real openPanelIndicatorWidth: button.width
  readonly property real openPanelIndicatorHeight: Math.max(Style.space(10), Math.round(Style.bar.iconSlot * 0.55))
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

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

  IpcHandler {
    target: "ochessy"

    function refresh(): void { root.broadcast("refresh") }
    function review(): void { root.reviewLast() }
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.togglePanel() }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.pillText
    labelVisible: false
    hasVisualContent: true
    keepSpace: true
    tooltipText: root.tooltipLabel
    fixedWidth: root.vertical ? root.barSize : root.chipW + 8
    fixedHeight: root.vertical ? root.chipW + 8 : root.barSize
    horizontalMargin: 4
    verticalPadding: 2

    onPressed: function(b) {
      if (b === Qt.RightButton) root.cycleTimeClass()
      else if (b === Qt.MiddleButton) root.reviewLast()
      else root.togglePanel()
    }

    BorderSurface {
      id: chip
      anchors.centerIn: parent
      width: root.vertical ? Math.max(22, parent.width - 6) : root.chipW
      height: root.vertical ? root.chipW : root.chipH
      radius: Style.cornerRadius
      color: Util.alpha(root.chipFill, root.opened ? 1 : 0.88)
      borderSpec: Border.controlSpec(root.opened ? "focus" : "normal", root.chipInk, root.chipFill)

      Row {
        anchors.centerIn: parent
        spacing: 4

        Text {
          text: "󰡗"
          color: root.chipInk
          font.family: button.fontFamily
          font.pixelSize: Style.font.body
          anchors.verticalCenter: parent.verticalCenter
        }

        Text {
          visible: !root.vertical
          text: root.pillText
          color: root.chipInk
          font.family: button.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
          anchors.verticalCenter: parent.verticalCenter
        }

        Text {
          visible: !root.vertical && root.deltaText !== ""
          text: root.deltaText
          color: root.chipInk
          opacity: 0.75
          font.family: button.fontFamily
          font.pixelSize: Style.font.bodySmall
          anchors.verticalCenter: parent.verticalCenter
        }
      }
    }
  }

  function cycleTimeClass() {
    persistSettings({ timeClass: Model.nextTimeClass(root.setting("timeClass", "auto")) })
    root.refresh()
  }
}
