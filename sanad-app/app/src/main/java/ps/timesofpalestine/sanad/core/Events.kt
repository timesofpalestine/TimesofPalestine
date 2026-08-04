package ps.timesofpalestine.sanad.core

import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import kotlin.random.Random

/**
 * The SANAD event engine — byte-compatible with the web board at
 * timesofpalestine.com/sanad/. Everything that happens is an append-only
 * event with a random id; state is derived by replaying the log; two devices
 * sync by exchanging events they don't already have, in any order, by any
 * carrier. Importing the same event twice changes nothing.
 *
 * Wire format, one event per line:  "SND1." + base64url(JSON)
 */
object Snd1 {
    private const val PREFIX = "SND1."
    private const val B64_FLAGS = Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING

    fun encode(events: List<JSONObject>): String =
        events.joinToString("\n") {
            PREFIX + Base64.encodeToString(it.toString().toByteArray(Charsets.UTF_8), B64_FLAGS)
        }

    fun decode(text: String): List<JSONObject> {
        val out = ArrayList<JSONObject>()
        for (raw in text.split(Regex("\\s+"))) {
            val line = raw.trim()
            if (!line.startsWith(PREFIX)) continue
            try {
                val json = String(Base64.decode(line.substring(PREFIX.length), B64_FLAGS), Charsets.UTF_8)
                val obj = JSONObject(json)
                if (obj.has("id") && obj.has("ty")) out.add(obj)
            } catch (_: Exception) { /* a mangled line never poisons the rest */ }
        }
        return out
    }

    fun uid(): String {
        val t = System.currentTimeMillis().toString(36)
        val r = (1..6).joinToString("") { Random.nextInt(36).toString(36) }
        return t + r
    }
}

/** A derived case: the replayed view the board renders. */
class CaseView(val event: JSONObject) {
    val id: String = event.getString("id")
    val ref: String = event.optString("ref")
    val createdAt: Long = event.optLong("ts")
    val by: JSONObject = event.optJSONObject("by") ?: JSONObject()
    private val c: JSONObject = event.optJSONObject("c") ?: JSONObject()
    val specialty: String get() = c.optString("specialty")
    val urgency: String get() = c.optString("urgency", "amber")
    val ageBand: String get() = c.optString("ageBand")
    val sex: String get() = c.optString("sex")
    val zone: String get() = c.optString("zone")
    val facility: String get() = c.optString("facility")
    val presentation: String get() = c.optString("presentation")
    val findings: String get() = c.optString("findings")
    val resources: String get() = c.optString("resources")
    val question: String get() = c.optString("question")
    val contact: String get() = c.optString("contact")

    var claimBy: String? = null
    var claimPk: JSONObject? = null
    val pk: JSONObject? = event.optJSONObject("pk")
    val thread = ArrayList<JSONObject>()
    var closed = false

    val status: String
        get() = when {
            closed -> "closed"
            thread.any { (it.optJSONObject("by")?.optString("r")) == "specialist" } -> "answered"
            claimBy != null -> "claimed"
            else -> "open"
        }
}

object Board {
    /** Replay events into cases, mirroring the web board's derive(). */
    fun derive(events: List<JSONObject>): List<CaseView> {
        val map = LinkedHashMap<String, CaseView>()
        for (e in events) if (e.optString("ty") == "case") map[e.getString("id")] = CaseView(e)
        for (e in events) {
            val c = map[e.optString("cid")] ?: continue
            when (e.optString("ty")) {
                "reply" -> c.thread.add(e)
                "claim" -> if (c.claimBy == null) {
                    c.claimBy = e.optJSONObject("by")?.optString("n")
                    c.claimPk = e.optJSONObject("pk")
                }
                "close" -> c.closed = true
            }
        }
        for (c in map.values) c.thread.sortBy { it.optLong("ts") }
        val rank = mapOf("red" to 0, "amber" to 1, "routine" to 2)
        return map.values.sortedWith(
            compareBy({ it.closed }, { rank[it.urgency] ?: 1 }, { it.createdAt }))
    }

    /** Merge incoming events into the log; returns how many were new. */
    fun merge(log: JSONArray, incoming: List<JSONObject>): Int {
        val have = HashSet<String>()
        for (i in 0 until log.length()) have.add(log.getJSONObject(i).getString("id"))
        var added = 0
        for (e in incoming) if (have.add(e.getString("id"))) { log.put(e); added++ }
        return added
    }
}
