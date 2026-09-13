import QtQuick
import QtQuick.Controls as QC
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "ochessy"
  ipcTarget: "ochessy"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  property var status: Model.defaultStatus()
  property int cursorIndex: 0
  property bool cursorActive: false
  property bool editingUsername: false
  property string usernameDraft: ""

  readonly property string pluginRoot: Model.pluginRootFrom(Qt.resolvedUrl("."), Quickshell.env("HOME"))
  readonly property string statusScript: pluginRoot + "/scripts/status.sh"
  readonly property string reviewScript: pluginRoot + "/scripts/review.sh"
  readonly property string username: Model.normalizeUsername(setting("username", ""))
  readonly property string timeClass: Model.normalizeTimeClass(setting("timeClass", "auto"))
  readonly property int depth: Model.normalizeDepth(setting("depth", 12))
  // 0 seconds disables the Leela pass entirely; Stockfish stays the primary
  // engine either way.
  readonly property int leelaSeconds: Model.normalizeLeelaSeconds(setting("leelaSeconds", 0))
  readonly property int leelaPositions: Model.normalizeLeelaPositions(setting("leelaPositions", 5))
  // Seconds per position instead of a fixed depth. Depth 18 costs 0.05s in a
  // simple endgame and 0.8s in a sharp middlegame, so a time budget spends
  // the effort where the position actually needs it.
  readonly property real moveTime: Model.normalizeMoveTime(setting("moveTime", 0))
  readonly property var ratingRows: Model.ratingRows(status)
  readonly property var extraRows: Model.extraStatRows(status)
  readonly property var games: status.games || []
  readonly property var actions: actionList()
  readonly property int gameOffset: actions.length

  readonly property color contentForeground: bar ? bar.foreground : Color.foreground
  readonly property string contentFontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color dim: Qt.darker(contentForeground, 1.55)
  readonly property color urgent: bar ? bar.urgent : Color.urgent

  function open() {
    refresh()
    if (username === "") {
      usernameDraft = ""
      editingUsername = true
    }
    root.controller.show()
    Qt.callLater(function() {
      if (root.opened) setCenterHoverRevealSuppressed(true)
      if (root.editingUsername && usernameField) usernameField.forceActiveFocus()
      else if (keyCatcher) keyCatcher.forceActiveFocus()
    })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    cursorActive = false
    editingUsername = false
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.open()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function setCenterHoverRevealSuppressed(value) {
    if (root.bar && "centerHoverRevealSuppressed" in root.bar)
      root.bar.centerHoverRevealSuppressed = value
  }

  function persistSettings(values) {
    var entry = { id: root.moduleName }
    for (var existing in root.settings) if (existing !== "id") entry[existing] = root.settings[existing]
    for (var key in values) entry[key] = values[key]
    root.settings = entry
    if (root.hostWidget && "settings" in root.hostWidget) root.hostWidget.settings = entry
    if (root.hostWidget && typeof root.hostWidget.persistSettings === "function")
      root.hostWidget.persistSettings(values)
    else if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function refresh() {
    if (statusProc.running) return
    statusProc.command = [statusScript, "--username", username, "--time-class", timeClass]
    statusProc.running = true
  }

  function commitUsername() {
    var next = Model.normalizeUsername(usernameDraft)
    editingUsername = false
    persistSettings({ username: next })
    Qt.callLater(root.refresh)
    if (keyCatcher) keyCatcher.forceActiveFocus()
  }

  function startEditingUsername() {
    usernameDraft = username
    editingUsername = true
    Qt.callLater(function() {
      if (usernameField) usernameField.forceActiveFocus()
    })
  }

  function cancelEditingUsername() {
    editingUsername = false
    usernameDraft = username
    if (keyCatcher) keyCatcher.forceActiveFocus()
  }

  function cycleTimeClass() {
    persistSettings({ timeClass: Model.nextTimeClass(timeClass) })
    Qt.callLater(root.refresh)
  }

  function reviewArgv(gameUrl) {
    var argv = [
      "omarchy-launch-or-focus-tui",
      "--app-id=org.omarchy.ochessy",
      reviewScript,
      "--username", username,
      "--time-class", timeClass,
      "--depth", String(depth),
      "--leela-seconds", String(leelaSeconds),
      "--leela-positions", String(leelaPositions),
      "--move-time", String(moveTime)
    ]
    if (gameUrl) argv.push("--game-url", gameUrl)
    return argv
  }

  // A review runs detached in its own terminal, so the panel cannot watch the
  // process. It can watch the result: a finished review lands in the cache and
  // bumps the stored-review count, which is what clears this flag.
  property bool reviewPending: false
  property int reviewBaseline: 0
  property int reviewWaited: 0

  function markReviewStarted() {
    var trend = root.status ? root.status.trend : null
    root.reviewBaseline = trend ? Number(trend.reviews || 0) : 0
    root.reviewWaited = 0
    root.reviewPending = true
  }

  function noteStatusArrived() {
    if (!root.reviewPending) return
    var trend = root.status ? root.status.trend : null
    if (trend && Number(trend.reviews || 0) > root.reviewBaseline) root.reviewPending = false
  }

  Timer {
    id: pendingTimer
    interval: 5000
    repeat: true
    running: root.reviewPending
    onTriggered: {
      root.reviewWaited += 1
      if (root.reviewWaited > 60) {
        root.reviewPending = false
        return
      }
      root.refresh()
    }
  }

  function reviewLast() {
    if (username === "") {
      startEditingUsername()
      return
    }
    Util.execArgv(reviewArgv(""))
    root.markReviewStarted()
  }

  function reviewGame(game) {
    if (username === "") {
      startEditingUsername()
      return
    }
    var url = game && game.url ? String(game.url) : ""
    Util.execArgv(reviewArgv(url))
    root.markReviewStarted()
  }

  function reviewGameAt(index) {
    if (index < 0 || index >= games.length) return
    reviewGame(games[index])
  }

  function actionList() {
    return [
      { id: "review", label: "Review last game", icon: "󰓥" },
      { id: "refresh", label: "Refresh stats", icon: "󰑐" },
      { id: "time", label: "Time class: " + timeClass, icon: "󰔟" }
    ]
  }

  function runAction(id) {
    if (id === "review") root.reviewLast()
    else if (id === "refresh") root.refresh()
    else if (id === "time") root.cycleTimeClass()
  }

  function cursorCount() {
    return actions.length + games.length
  }

  function moveCursor(dx, dy) {
    if (editingUsername) return
    cursorActive = true
    if (dy === 0) return
    var max = Math.max(0, cursorCount() - 1)
    cursorIndex = Math.max(0, Math.min(max, cursorIndex + dy))
  }

  function activateCursor() {
    if (editingUsername) return
    if (!cursorActive) {
      cursorActive = true
      return
    }
    if (cursorIndex < actions.length) {
      runAction(actions[cursorIndex].id)
      return
    }
    reviewGameAt(cursorIndex - gameOffset)
  }

  onOpenedChanged: if (opened) {
    cursorActive = false
    cursorIndex = 0
    if (panelFlick) panelFlick.contentY = 0
    refresh()
  }

  onUsernameChanged: if (opened && username !== "") refresh()
  onTimeClassChanged: if (opened) refresh()

  Timer {
    // Closed, nothing is on screen but the chip, and the API data behind it
    // is cached for minutes anyway: polling every five minutes forever was
    // spending requests nobody was reading.
    interval: root.opened ? 120000 : 900000
    repeat: true
    running: root.username !== ""
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Process {
    id: statusProc
    running: false
    command: [root.statusScript]
    stdout: StdioCollector {
      id: statusStdout
      waitForEnd: true
    }
    stderr: StdioCollector {
      id: statusStderr
      waitForEnd: true
    }
    onExited: function(exitCode) {
      var parsed = Model.parseStatus(statusStdout.text)
      if (exitCode !== 0 && !parsed.lastError)
        parsed.lastError = String(statusStderr.text || "Could not load Chess.com stats").trim()
      root.status = parsed
      root.noteStatusArrived()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(440))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(640))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: root.editingUsername
      onMoveRequested: function(dx, dy) { root.moveCursor(dx, dy) }
      onActivateRequested: root.activateCursor()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") root.reviewLast()
        else if (t === "s" || t === "S") root.refresh()
        else if (t === "t" || t === "T") root.cycleTimeClass()
        else if (t === "u" || t === "U") root.startEditingUsername()
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        QC.ScrollBar.vertical: QC.ScrollBar { policy: QC.ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

          PanelHero {
            width: parent.width
            title: Model.titleName(root.status)
            meta: Model.heroMeta(root.status)
            detail: Model.heroDetail(root.status)
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            iconComponent: Component {
              Text {
                text: "󰡗"
                color: Color.accent
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.display
              }
            }
          }

          Text {
            visible: String(root.status.lastError || "") !== ""
            width: parent.width
            text: String(root.status.lastError || "")
            color: root.urgent
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          Text {
            visible: !root.editingUsername
            width: parent.width
            text: root.username !== "" ? "Username  " + root.username + "  (u to edit)" : "Click below or press u to set your Chess.com username"
            color: root.dim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap

            HoverHandler { cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: root.startEditingUsername() }
          }

          TextField {
            id: usernameField
            visible: root.editingUsername
            width: parent.width
            placeholderText: "Chess.com username"
            text: root.usernameDraft
            foreground: root.contentForeground
            font.family: root.contentFontFamily
            onTextChanged: root.usernameDraft = text
            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Escape) {
                root.cancelEditingUsername()
                event.accepted = true
              } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                root.commitUsername()
                event.accepted = true
              }
            }
          }

          PanelSeparator { foreground: root.contentForeground }

          PanelSectionHeader {
            text: "RATINGS"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
          }

          Repeater {
            model: root.ratingRows

            Row {
              required property var modelData
              width: column.width
              spacing: Style.space(10)

              Text {
                width: Style.space(70)
                text: String(modelData.label || "")
                color: modelData.id === root.status.timeClass ? Color.accent : root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.body
                font.bold: modelData.id === root.status.timeClass
              }

              Text {
                width: Style.space(56)
                text: Number(modelData.rating || 0) > 0 ? String(modelData.rating) : "—"
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }

              Text {
                width: parent.width - Style.space(136)
                text: Number(modelData.best || 0) > 0
                  ? "best " + modelData.best + " · " + modelData.record
                  : String(modelData.record || "")
                color: root.dim
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
                anchors.verticalCenter: parent.verticalCenter
              }
            }
          }

          Repeater {
            model: root.extraRows

            Row {
              required property var modelData
              width: column.width
              spacing: Style.space(10)

              Text {
                width: Style.space(110)
                text: String(modelData.label || "")
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                text: String(modelData.value || "")
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
                font.bold: true
              }

              Text {
                visible: String(modelData.detail || "") !== ""
                text: String(modelData.detail || "")
                color: root.dim
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
              }
            }
          }

          Text {
            visible: root.extraRows.length === 0 && root.username !== "" && root.status.ok
            width: parent.width
            text: "No tactics / lessons / Puzzle Rush stats on this profile yet."
            color: root.dim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          PanelSeparator { foreground: root.contentForeground }

          PanelSectionHeader {
            text: "ACTIONS"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
          }

          Repeater {
            model: root.actions

            Button {
              required property var modelData
              required property int index
              width: column.width
              text: modelData.label
              iconText: modelData.icon
              bordered: true
              leftAlign: true
              hasCursor: root.cursorActive && root.cursorIndex === index
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
              onClicked: root.runAction(modelData.id)
              onHovered: function(on) {
                if (on) {
                  root.cursorActive = true
                  root.cursorIndex = index
                }
              }
            }
          }

          Text {
            visible: root.reviewPending
            width: parent.width
            text: "Reviewing… the report opens in a terminal, and lands here when it finishes."
            color: root.dim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          PanelSeparator { foreground: root.contentForeground }

          PanelSectionHeader {
            text: "TRENDS"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
          }

          Text {
            visible: Model.trendHeadline(root.status) === ""
            width: parent.width
            text: "Review a few games and what repeats across them shows up here."
            color: root.dim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          Column {
            visible: Model.trendHeadline(root.status) !== ""
            width: parent.width
            spacing: 3

            Text {
              width: parent.width
              text: Model.trendHeadline(root.status)
              color: root.contentForeground
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
              font.bold: true
              elide: Text.ElideRight
            }

            Text {
              width: parent.width
              text: Model.trendDetail(root.status)
              color: root.dim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.bodySmall
              elide: Text.ElideRight
            }

            Text {
              visible: Model.trendThemes(root.status) !== ""
              width: parent.width
              text: "Recurring: " + Model.trendThemes(root.status)
              color: root.dim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.bodySmall
              elide: Text.ElideRight
            }

            Text {
              visible: Model.ratingSparkline(root.status) !== ""
              width: parent.width
              text: Model.ratingSparkline(root.status) + "  " + root.timeClass
              color: Color.accent
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
            }
          }

          PanelSeparator { foreground: root.contentForeground }

          PanelSectionHeader {
            text: "RECENT GAMES"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
          }

          Text {
            visible: root.games.length === 0
            width: parent.width
            text: root.username === "" ? "Set a username to load games." : "No recent standard games in the public archive."
            color: root.dim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          Repeater {
            model: root.games

            Button {
              required property var modelData
              required property int index
              width: column.width
              text: Model.gameLabel(modelData)
              iconText: modelData.result === "win" ? "󰄬" : (modelData.result === "draw" ? "󰔷" : "󰅖")
              bordered: true
              leftAlign: true
              hasCursor: root.cursorActive && root.cursorIndex === (root.gameOffset + index)
              foreground: modelData.result === "win"
                ? Color.accent
                : (modelData.result === "loss" ? Color.urgent : root.contentForeground)
              fontFamily: root.contentFontFamily
              tooltipText: Model.gameDetail(modelData)
              onClicked: root.reviewGame(modelData)
              onHovered: function(on) {
                if (on) {
                  root.cursorActive = true
                  root.cursorIndex = root.gameOffset + index
                }
              }
            }
          }

          Text {
            width: parent.width
            text: "Review opens a terminal with Stockfish notes, Chess.com lessons, and checked third-party links. r last game · s refresh · t time class · u username"
            color: root.dim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }
        }
      }
    }
  }
}
