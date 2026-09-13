.pragma library

var TIME_CLASSES = ["auto", "bullet", "blitz", "rapid", "daily"]

function defaultStatus() {
  return {
    ok: false,
    ready: false,
    username: "",
    name: "",
    title: "",
    country: "",
    joined: 0,
    lastOnline: 0,
    followers: 0,
    league: "",
    fide: 0,
    timeClass: "blitz",
    rating: 0,
    bestRating: 0,
    record: { win: 0, loss: 0, draw: 0 },
    ratings: {},
    tactics: null,
    lessons: null,
    puzzleRush: null,
    games: [],
    packagesOk: true,
    missingPackages: [],
    lastError: ""
  }
}

function parseStatus(raw) {
  var text = String(raw || "").trim()
  if (text === "") return defaultStatus()
  try {
    var parsed = JSON.parse(text)
    if (!parsed || typeof parsed !== "object") return defaultStatus()
    parsed.ok = parsed.ok !== false
    parsed.games = Array.isArray(parsed.games) ? parsed.games : []
    parsed.missingPackages = Array.isArray(parsed.missingPackages) ? parsed.missingPackages : []
    parsed.ratings = parsed.ratings && typeof parsed.ratings === "object" ? parsed.ratings : {}
    parsed.record = parsed.record && typeof parsed.record === "object"
      ? parsed.record
      : { win: 0, loss: 0, draw: 0 }
    return parsed
  } catch (e) {
    var failed = defaultStatus()
    failed.lastError = "Failed to parse Chess.com status"
    return failed
  }
}

function fileUrlToPath(url) {
  var value = String(url || "")
  if (value.indexOf("file:") !== 0) return value.replace(/\/+$/, "")
  try {
    var parsed = new URL(value)
    var path = decodeURIComponent(parsed.pathname || "")
    if (!path) return value.replace(/\/+$/, "")
    if (path.charAt(0) !== "/") path = "/" + path
    return path.replace(/\/+$/, "")
  } catch (e) {
    value = value.replace(/^file:\/\//, "").replace(/^localhost/, "")
    if (value.charAt(0) !== "/") value = "/" + value
    return value.replace(/\/+$/, "")
  }
}

function pluginRootFrom(resolvedUrl, home) {
  var fromUrl = fileUrlToPath(resolvedUrl)
  if (fromUrl.indexOf("/") === 0 && fromUrl.indexOf("://") < 0) return fromUrl
  return String(home || "") + "/.config/omarchy/plugins/ochessy"
}

function normalizeUsername(value) {
  return String(value || "").replace(/^\s+|\s+$/g, "").replace(/^@/, "")
}

function normalizeTimeClass(value) {
  var key = String(value || "auto").toLowerCase()
  for (var i = 0; i < TIME_CLASSES.length; i++) {
    if (TIME_CLASSES[i] === key) return key
  }
  return "auto"
}

function nextTimeClass(value) {
  var current = normalizeTimeClass(value)
  for (var i = 0; i < TIME_CLASSES.length; i++) {
    if (TIME_CLASSES[i] === current)
      return TIME_CLASSES[(i + 1) % TIME_CLASSES.length]
  }
  return "auto"
}

function normalizeDepth(value) {
  var n = parseInt(String(value || ""), 10)
  if (!isFinite(n)) n = 12
  if (n < 8) n = 8
  if (n > 18) n = 18
  return n
}

function normalizeMoveTime(value) {
  var n = Number(value)
  if (!isFinite(n) || n < 0) n = 0
  if (n > 5) n = 5
  return Math.round(n * 10) / 10
}

function normalizeLeelaSeconds(value) {
  var n = parseInt(String(value || ""), 10)
  if (!isFinite(n)) n = 0
  if (n < 0) n = 0
  if (n > 30) n = 30
  return n
}

function normalizeLeelaPositions(value) {
  var n = parseInt(String(value || ""), 10)
  if (!isFinite(n)) n = 5
  if (n < 0) n = 0
  if (n > 8) n = 8
  return n
}

var SPARK = ["\u2581", "\u2582", "\u2583", "\u2584", "\u2585", "\u2586", "\u2587", "\u2588"]

// Chess.com reports both players' ratings on every game, so the user's own
// rating comes from whichever side they were.
function userRating(game) {
  if (!game) return 0
  return Number(game.userColor === "white" ? game.whiteRating : game.blackRating) || 0
}

// Oldest to newest, restricted to one pool: mixing bullet into a blitz curve
// would draw a sawtooth that means nothing.
function ratingSeries(status, timeClass) {
  var games = (status && status.games) || []
  var klass = normalizeTimeClass(timeClass)
  var out = []
  for (var i = games.length - 1; i >= 0; i--) {
    var game = games[i]
    if (!game) continue
    if (klass !== "auto" && String(game.timeClass) !== klass) continue
    var rating = userRating(game)
    if (rating > 0) out.push(rating)
  }
  return out
}

function ratingDelta(status) {
  var series = ratingSeries(status, status && status.timeClass)
  if (series.length < 2) return 0
  return series[series.length - 1] - series[series.length - 2]
}

function deltaLabel(status) {
  var delta = ratingDelta(status)
  if (!delta) return ""
  return (delta > 0 ? "\u25b2" : "\u25bc") + Math.abs(delta)
}

function sparkline(values, width) {
  if (!values || values.length < 2) return ""
  var span = width || 16
  var points = values.slice(Math.max(0, values.length - span))
  var low = points[0]
  var high = points[0]
  for (var i = 1; i < points.length; i++) {
    if (points[i] < low) low = points[i]
    if (points[i] > high) high = points[i]
  }
  var range = high - low
  var out = ""
  for (var j = 0; j < points.length; j++) {
    var level = range === 0 ? 3 : Math.round((points[j] - low) / range * 7)
    out += SPARK[Math.max(0, Math.min(7, level))]
  }
  return out
}

function ratingSparkline(status) {
  return sparkline(ratingSeries(status, status && status.timeClass), 18)
}

function trendOf(status) {
  var trend = status && status.trend
  return trend && typeof trend === "object" ? trend : null
}

function trendHeadline(status) {
  var trend = trendOf(status)
  if (!trend || !trend.reviews) return ""
  var direction = Number(trend.accuracyTrend || 0)
  var arrow = direction > 0.5 ? " \u25b2" : (direction < -0.5 ? " \u25bc" : "")
  return trend.accuracy + "% avg accuracy" + arrow + " \u00b7 " + trend.reviews + " reviewed"
}

function trendDetail(status) {
  var trend = trendOf(status)
  if (!trend || !trend.reviews) return ""
  var bits = []
  if (trend.blunders) bits.push(trend.blunders + " blunders/game")
  if (trend.missedChances) bits.push(trend.missedChances + " chances missed/game")
  if (trend.worstPhase) bits.push("weakest: " + trend.worstPhase)
  return bits.join(" \u00b7 ")
}

function trendThemes(status) {
  var trend = trendOf(status)
  if (!trend || !trend.themes || !trend.themes.length) return ""
  return trend.themes.join(", ").replace(/_/g, " ")
}

function pad2(n) {
  return n < 10 ? "0" + n : String(n)
}

function formatWhen(ts) {
  var n = Number(ts || 0)
  if (!n) return ""
  var d = new Date(n * 1000)
  if (isNaN(d.getTime())) return ""
  return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate())
}

function formatRecord(record) {
  var rec = record && typeof record === "object" ? record : {}
  return Number(rec.win || 0) + "W " + Number(rec.loss || 0) + "L " + Number(rec.draw || 0) + "D"
}

function titleName(status) {
  var title = String(status && status.title ? status.title : "")
  var name = String(status && status.name ? status.name : "")
  var user = String(status && status.username ? status.username : "")
  if (title && user) return title + " " + user
  return user || "Chess.com"
}

function heroMeta(status) {
  if (!status || status.lastError) return status && status.lastError ? "Needs attention" : "Set a username"
  if (!status.username) return "Set a username"
  if (!status.ok) return "Could not load profile"
  var bits = []
  if (status.timeClass) bits.push(String(status.timeClass))
  if (status.league) bits.push(String(status.league))
  if (status.country) bits.push(String(status.country))
  return bits.join(" · ") || "Profile"
}

function heroDetail(status) {
  var rating = Number(status && status.rating ? status.rating : 0)
  if (rating > 0) return String(rating)
  if (status && status.username) return "—"
  return "Setup"
}

function ratingRows(status) {
  var ratings = status && status.ratings ? status.ratings : {}
  var keys = ["bullet", "blitz", "rapid", "daily"]
  var rows = []
  for (var i = 0; i < keys.length; i++) {
    var key = keys[i]
    var row = ratings[key]
    if (!row || typeof row !== "object") {
      rows.push({ id: key, label: key, rating: 0, best: 0, record: "—" })
      continue
    }
    rows.push({
      id: key,
      label: key,
      rating: Number(row.rating || 0),
      best: Number(row.best || 0),
      record: formatRecord(row.record)
    })
  }
  return rows
}

function extraStatRows(status) {
  var rows = []
  var tactics = status && status.tactics
  if (tactics && typeof tactics === "object" && Number(tactics.highest || 0) > 0)
    rows.push({ label: "Tactics", value: String(tactics.highest), detail: tactics.lowest ? "low " + tactics.lowest : "" })
  var lessons = status && status.lessons
  if (lessons && typeof lessons === "object" && Number(lessons.highest || 0) > 0)
    rows.push({ label: "Lessons", value: String(lessons.highest), detail: "" })
  var rush = status && status.puzzleRush
  if (rush && typeof rush === "object") {
    var best = Number(rush.best || 0)
    var daily = Number(rush.daily || 0)
    if (best > 0 || daily > 0)
      rows.push({ label: "Puzzle Rush", value: best > 0 ? String(best) : String(daily), detail: daily > 0 ? "today " + daily : "" })
  }
  if (Number(status && status.followers ? status.followers : 0) > 0)
    rows.push({ label: "Followers", value: String(status.followers), detail: "" })
  if (Number(status && status.fide ? status.fide : 0) > 0)
    rows.push({ label: "FIDE", value: String(status.fide), detail: "" })
  if (status && status.lastOnline)
    rows.push({ label: "Last online", value: formatWhen(status.lastOnline), detail: "" })
  if (status && status.joined)
    rows.push({ label: "Joined", value: formatWhen(status.joined), detail: "" })
  return rows
}

function resultMark(result) {
  var value = String(result || "")
  if (value === "win") return "W"
  if (value === "draw") return "D"
  if (value === "loss") return "L"
  return "·"
}

function gameLabel(game) {
  if (!game) return "Game"
  var opponent = String(game.opponent || "opponent")
  var klass = String(game.timeClass || "game")
  return resultMark(game.result) + " vs " + opponent + " · " + klass
}

function gameDetail(game) {
  if (!game) return ""
  var bits = []
  if (game.userColor) bits.push(String(game.userColor))
  if (game.endTime) bits.push(formatWhen(game.endTime))
  if (game.rated === false) bits.push("unrated")
  return bits.join(" · ")
}

function barLabel(status) {
  var rating = Number(status && status.rating ? status.rating : 0)
  if (rating > 0) return String(rating)
  if (status && status.username) return "Chess"
  return "Chess"
}

function barTooltip(status) {
  if (!status || !status.username) return "OChessy · set a Chess.com username"
  if (status.lastError) return "OChessy · " + String(status.lastError)
  var rating = Number(status.rating || 0)
  var klass = String(status.timeClass || "rating")
  var rec = formatRecord(status.record)
  if (rating > 0) return rating + " " + klass + " · " + rec
  return String(status.username) + " · " + rec
}
