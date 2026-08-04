package ps.timesofpalestine.sanad

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import ps.timesofpalestine.sanad.core.Board
import ps.timesofpalestine.sanad.core.Snd1
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * SANAD v0.1 — bitchat for medicine, the native alpha.
 * One screen, three jobs: the triage board, the new-case form, the carrier
 * (share out / paste in). Packet-compatible with the web board; the BLE mesh
 * arrives in v0.3 (see README).
 */
class MainActivity : Activity() {

    private val specialties = listOf(
        "General surgery", "Orthopaedics / trauma", "Plastics & burns", "Vascular",
        "Neurosurgery", "Paediatrics", "Paediatric surgery", "Obstetrics",
        "Anaesthesia / ICU", "Infectious disease", "Wound & stoma care",
        "Nephrology / dialysis", "Ophthalmology", "Maxillofacial", "Radiology",
        "Internal medicine", "Nutrition", "Mental health", "Physiotherapy / rehab")
    private val zones = listOf("North Gaza", "Gaza City", "Deir al-Balah",
        "Khan Younis", "Rafah", "West Bank", "Displaced / outside", "Worldwide")
    private val urgencies = listOf("red", "amber", "routine")

    private lateinit var root: LinearLayout
    private fun prefs() = getSharedPreferences("sanad", MODE_PRIVATE)

    private fun log(): JSONArray = JSONArray(prefs().getString("events", "[]"))
    private fun saveLog(a: JSONArray) { prefs().edit().putString("events", a.toString()).apply() }
    private fun sent(): MutableSet<String> =
        prefs().getStringSet("sent", emptySet())!!.toMutableSet()
    private fun saveSent(s: Set<String>) { prefs().edit().putStringSet("sent", s).apply() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = dp(14); setPadding(pad, pad, pad, dp(40))
        }
        scroll.addView(root)
        setContentView(scroll)
        handleShared(intent)
        renderBoard()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShared(intent)
        renderBoard()
    }

    /** Packets shared at us from bitchat / WhatsApp / the web page. */
    private fun handleShared(i: Intent?) {
        val text = i?.getStringExtra(Intent.EXTRA_TEXT) ?: return
        val events = Snd1.decode(text)
        if (events.isEmpty()) return
        val a = log(); val n = Board.merge(a, events); saveLog(a)
        if (n > 0) toast("+$n")
    }

    // ---------------- board ----------------

    private fun renderBoard() {
        root.removeAllViews()
        header("SANAD", "بيتشات للطب — cases only, works without internet · not a medical service")
        rowButtons(
            "＋ New case" to { renderForm() },
            "Carrier ⇅" to { renderCarrier() })

        val cases = Board.derive(jsonList(log()))
        if (cases.isEmpty()) {
            para("No cases on this device yet. Post one, or import packets from " +
                 "a colleague — bitchat channel ${ps.timesofpalestine.sanad.core.Mesh.CHANNEL}, " +
                 "WhatsApp, or the web board at timesofpalestine.com/sanad/.")
            return
        }
        val df = SimpleDateFormat("MM-dd HH:mm", Locale.US)
        for (c in cases) {
            val box = card(when (c.urgency) { "red" -> 0xFFA61B2B.toInt()
                "routine" -> 0xFF1F5E52.toInt() else -> 0xFFA8720F.toInt() })
            box.addView(bold("${c.ref} · ${c.specialty} · ${c.urgency.uppercase()} · ${c.status.uppercase()}"))
            box.addView(small("${c.ageBand} · ${c.sex} · ${c.zone} · ${c.facility} · ${df.format(Date(c.createdAt))}"))
            box.addView(bold("Q: ${c.question}"))
            box.addView(small(c.presentation))
            if (c.claimBy != null) box.addView(small("Claimed by ${c.claimBy}"))
            for (m in c.thread) {
                val who = m.optJSONObject("by")?.optString("n") ?: "?"
                val body = if (m.has("enc"))
                    "🔒 encrypted for the case participants (decryption arrives in v0.2 — open on the web board)"
                else m.optString("text")
                box.addView(small("↳ $who: $body"))
            }
            val actions = LinearLayout(this)
            actions.addView(smallButton("Reply") { replyDialog(c.id) })
            actions.addView(smallButton("Claim") { emit(JSONObject().put("ty", "claim").put("cid", c.id)) })
            box.addView(actions)
            root.addView(box)
        }
    }

    // ---------------- new case ----------------

    private fun renderForm() {
        root.removeAllViews()
        header("New case", "Plain words. No names, no ID numbers, no faces. One clear question.")
        val spec = spinner(specialties); labeled("Specialty", spec)
        val urg = spinner(urgencies); labeled("Urgency (red 1h · amber 6h · routine 48h)", urg); urg.setSelection(1)
        val zone = spinner(zones); labeled("Zone", zone)
        val fac = field("Facility or medical point")
        val age = field("Age band (e.g. adult 18–49, 5–11)")
        val sex = field("Sex (F / M / unknown)")
        val pres = area("What happened and what you see")
        val find = area("Findings, vitals, what you have done")
        val res = area("What you have and what you lack")
        val q = area("The one question you need answered")
        val contact = field("How the specialist reaches you (when the network returns)")
        val name = field("Your name or initials").apply { setText(prefs().getString("me", "")) }
        val consent = CheckBox(this).apply { text = "The patient or guardian gave verbal consent to discuss this case." }
        val deid = CheckBox(this).apply { text = "I removed names, ID numbers, dates of birth and faces." }
        root.addView(consent); root.addView(deid)
        rowButtons(
            "Save & queue" to save@{
                if (!consent.isChecked || !deid.isChecked) { toast("Both boxes have to be ticked"); return@save }
                if (q.text.isBlank() || pres.text.isBlank()) { toast("Presentation and question are required"); return@save }
                prefs().edit().putString("me", name.text.toString().trim()).apply()
                val d = Date()
                val ref = "GZ-" + SimpleDateFormat("MMdd", Locale.US).format(d) +
                    "-A" + ((log().length() % 90) + 10)
                emit(JSONObject().put("ty", "case").put("ref", ref).put("c", JSONObject()
                    .put("specialty", spec.selectedItem.toString())
                    .put("urgency", urg.selectedItem.toString())
                    .put("ageBand", age.text.toString().trim())
                    .put("sex", sex.text.toString().trim())
                    .put("zone", zone.selectedItem.toString())
                    .put("facility", fac.text.toString().trim())
                    .put("presentation", pres.text.toString().trim())
                    .put("findings", find.text.toString().trim())
                    .put("resources", res.text.toString().trim())
                    .put("question", q.text.toString().trim())
                    .put("contact", contact.text.toString().trim())))
                shareUnsent()   // the hand-off IS the point: straight to the share sheet
            },
            "Back" to { renderBoard() })
    }

    // ---------------- carrier ----------------

    private fun renderCarrier() {
        root.removeAllViews()
        val unsentCount = jsonList(log()).count { !sent().contains(it.getString("id")) }
        header("Carrier", "One packet format, every path: share to bitchat (channel " +
            "${ps.timesofpalestine.sanad.core.Mesh.CHANNEL}), WhatsApp, AirDrop/Quick Share — " +
            "or paste packets you received. Importing twice never duplicates.")
        rowButtons(
            "Share new ($unsentCount)" to { shareUnsent() },
            "Share everything" to { share(jsonList(log())) })
        val imp = area("Paste SND1 packets here")
        rowButtons(
            "Import" to {
                val got = Snd1.decode(imp.text.toString())
                val a = log(); val n = Board.merge(a, got); saveLog(a)
                toast(if (n > 0) "imported $n" else "no new packets")
                renderBoard()
            },
            "Back" to { renderBoard() })
    }

    // ---------------- engine glue ----------------

    private fun emit(e: JSONObject) {
        e.put("id", Snd1.uid()).put("ts", System.currentTimeMillis())
        e.put("by", JSONObject().put("n", prefs().getString("me", "").orEmpty().ifBlank { "anon" })
            .put("r", "field").put("c", ""))
        val a = log(); a.put(e); saveLog(a)
        renderBoard()
    }

    private fun replyDialog(cid: String) {
        val input = EditText(this).apply { minLines = 3 }
        AlertDialog.Builder(this).setTitle("Your advice / reply")
            .setView(input)
            .setPositiveButton("Send") { _, _ ->
                val text = input.text.toString().trim()
                if (text.isNotEmpty()) emit(JSONObject().put("ty", "reply").put("cid", cid).put("text", text))
            }
            .setNegativeButton("Cancel", null).show()
    }

    private fun shareUnsent() {
        val all = jsonList(log()); val s = sent()
        val q = all.filter { !s.contains(it.getString("id")) }
        if (q.isEmpty()) { toast("nothing to send"); renderBoard(); return }
        share(q)
    }

    private fun share(events: List<JSONObject>) {
        val text = Snd1.encode(events)
        val s = sent(); events.forEach { s.add(it.getString("id")) }; saveSent(s)
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text)
        }, "Send Sanad packets"))
        renderBoard()
    }

    private fun jsonList(a: JSONArray): List<JSONObject> =
        (0 until a.length()).map { a.getJSONObject(it) }

    // ---------------- tiny view helpers ----------------

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun toast(m: String) = Toast.makeText(this, m, Toast.LENGTH_SHORT).show()

    private fun header(title: String, sub: String) {
        root.addView(TextView(this).apply {
            text = title; textSize = 26f; setTypeface(null, Typeface.BOLD) })
        root.addView(small(sub))
    }
    private fun para(s: String) { root.addView(TextView(this).apply { text = s; setPadding(0, dp(10), 0, 0) }) }
    private fun bold(s: String) = TextView(this).apply { text = s; setTypeface(null, Typeface.BOLD) }
    private fun small(s: String) = TextView(this).apply { text = s; textSize = 13f; alpha = 0.8f }
    private fun field(hint: String): EditText {
        val e = EditText(this).apply { this.hint = hint; inputType = InputType.TYPE_CLASS_TEXT }
        root.addView(e); return e
    }
    private fun area(hint: String): EditText {
        val e = EditText(this).apply {
            this.hint = hint; minLines = 2
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        }
        root.addView(e); return e
    }
    private fun spinner(items: List<String>): Spinner = Spinner(this).apply {
        adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, items)
    }
    private fun labeled(label: String, v: View) { root.addView(small(label)); root.addView(v) }
    private fun smallButton(label: String, onClick: () -> Unit): Button =
        Button(this).apply { text = label; setOnClickListener { onClick() } }
    private fun rowButtons(vararg items: Pair<String, () -> Unit>) {
        val row = LinearLayout(this).apply { gravity = Gravity.START }
        for ((label, fn) in items) row.addView(smallButton(label, fn))
        root.addView(row)
    }
    private fun card(edge: Int): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        val pad = dp(10); setPadding(pad, pad, pad, pad)
        setBackgroundColor(0x14000000)
        val lp = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT)
        lp.setMargins(0, dp(10), 0, 0); layoutParams = lp
        val stripe = View(this@MainActivity).apply {
            setBackgroundColor(edge)
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(4))
        }
        addView(stripe, 0)
    }
}
