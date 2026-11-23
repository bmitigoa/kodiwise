package com.kodiwise.app

import com.google.gson.annotations.SerializedName

/** One turn sent to kodiwise-chat. Text only: the server keeps nothing. */
data class ChatTurn(val role: String, val text: String)

data class ChatRequestBody(val messages: List<ChatTurn>)

data class ChatListing(
    val title: String = "",
    val area: String = "",
    @SerializedName("rent_kes") val rentKes: Double = 0.0,
    val bedrooms: Int? = null,
    val bathrooms: Int? = null,
    val badge: String? = null
)

/** A tool-backed card. The server builds these from tool results, never from the model's wording. */
data class ChatCard(
    val type: String = "",
    // estimate
    val area: String = "",
    @SerializedName("estimate_kes") val estimateKes: Double = 0.0,
    @SerializedName("range_low_kes") val rangeLowKes: Double = 0.0,
    @SerializedName("range_high_kes") val rangeHighKes: Double = 0.0,
    val confidence: String = "high",
    val bedrooms: Int? = null,
    val bathrooms: Int? = null,
    @SerializedName("asking_rent_kes") val askingRentKes: Double? = null,
    val verdict: String? = null,
    // areas
    val title: String = "",
    val budget: String? = null,
    val areas: List<ChatAreaRow> = emptyList(),
    val comfortable: List<ChatAreaRow> = emptyList(),
    val stretch: List<ChatAreaRow> = emptyList(),
    val thin: List<String> = emptyList(),
    // listings
    val total: Int? = null,
    val listings: List<ChatListing> = emptyList()
)

data class ChatAreaRow(
    val area: String? = null,
    @SerializedName("estimate_kes") val estimateKes: Double? = null,
    @SerializedName("range_low_kes") val rangeLowKes: Double? = null,
    @SerializedName("range_high_kes") val rangeHighKes: Double? = null,
    val confidence: String? = null,
    @SerializedName("distance_km") val distanceKm: Double? = null
)

data class ChatReply(
    val status: String = "ok",
    val reply: String = "",
    val cards: List<ChatCard> = emptyList(),
    @SerializedName("remaining_today") val remainingToday: Int = 0,
    @SerializedName("show_assistant_button") val showAssistantButton: Boolean = false
)

enum class ChatRole { USER, BOT }

/** Normal answers count as conversation context; limit and error bubbles never go back to the server. */
enum class ChatKind { NORMAL, LIMIT, ERROR }

data class ChatMessage(
    val role: ChatRole,
    val text: String,
    val cards: List<ChatCard> = emptyList(),
    val kind: ChatKind = ChatKind.NORMAL,
    val showAssistantButton: Boolean = false
)

/** Pure logic for the "Ask KodiWise" screen (no Android types, so it unit-tests on the JVM). */
object ChatLogic {
    const val MAX_HISTORY = 6
    const val MAX_CHARS = 500
    const val STATUS_OK = "ok"
    const val STATUS_LIMIT_USER = "limit_user"
    const val STATUS_LIMIT_GLOBAL = "limit_global"
    const val STATUS_BUSY = "busy"

    /** A message that is not blank and fits the server's limit. */
    fun canSend(text: String?): Boolean {
        val t = text.orEmpty().trim()
        return t.isNotEmpty() && t.length <= MAX_CHARS
    }

    /** Last [MAX_HISTORY] real turns, text trimmed, starting on a user turn and ending on one. */
    fun buildRequest(messages: List<ChatMessage>): ChatRequestBody {
        val turns = messages
            .filter { it.kind == ChatKind.NORMAL && it.text.isNotBlank() }
            .takeLast(MAX_HISTORY)
            .map { ChatTurn(if (it.role == ChatRole.USER) "user" else "model", it.text.trim().take(MAX_CHARS)) }
            .dropWhile { it.role != "user" }
        return ChatRequestBody(turns)
    }

    fun isLimit(status: String): Boolean = status != STATUS_OK

    /** Daily limits end the chat for today; "busy" is temporary, so typing stays on. */
    fun inputDisabled(status: String): Boolean = status == STATUS_LIMIT_USER || status == STATUS_LIMIT_GLOBAL

    fun kindFor(status: String): ChatKind = if (status == STATUS_OK) ChatKind.NORMAL else ChatKind.LIMIT

    /** Maps the server's verdict text to the same verdicts the fair-rent sheet uses. */
    fun verdict(v: String?): FairVerdict = when (v) {
        "above_estimated_range" -> FairVerdict.ABOVE
        "within_estimated_range" -> FairVerdict.WITHIN
        "below_estimated_range" -> FairVerdict.BELOW
        else -> FairVerdict.NO_VERDICT
    }

    /** An area row the app can draw: all numbers present and a real range. */
    fun toAreaRow(r: ChatAreaRow): AreaRow? {
        val name = r.area ?: return null
        val est = r.estimateKes ?: return null
        val lo = r.rangeLowKes ?: return null
        val hi = r.rangeHighKes ?: return null
        if (name.isBlank() || est <= 0 || hi < lo) return null
        return AreaRow(name, est, lo, hi, r.confidence ?: "high", r.distanceKm)
    }

    fun toAreaRow(c: ChatCard): AreaRow? =
        toAreaRow(ChatAreaRow(c.area, c.estimateKes, c.rangeLowKes, c.rangeHighKes, c.confidence, null))

    /** Message for an HTTP failure that is not a normal chat answer. */
    fun errorMessage(code: Int?): String = when (code) {
        401 -> "Please sign in again to use the chat."
        422 -> "That message couldn't be sent. Try rephrasing it."
        502, 503, 504 -> "The assistant couldn't answer just now. Please try again."
        else -> "Couldn't reach the assistant. Check your connection and try again."
    }

    fun remainingText(remaining: Int?): String? = when {
        remaining == null -> null
        remaining <= 0 -> "No messages left today"
        remaining == 1 -> "1 message left today"
        else -> "$remaining messages left today"
    }
}
