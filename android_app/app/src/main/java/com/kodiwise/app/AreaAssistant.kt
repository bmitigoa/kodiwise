package com.kodiwise.app

import com.google.gson.JsonParser
import com.google.gson.annotations.SerializedName

/** One neighbourhood in a /areas-within-budget answer. */
data class AreaRow(
    val area: String = "",
    @SerializedName("estimate_kes") val estimateKes: Double = 0.0,
    @SerializedName("range_low_kes") val rangeLowKes: Double = 0.0,
    @SerializedName("range_high_kes") val rangeHighKes: Double = 0.0,
    @SerializedName("location_confidence") val locationConfidence: String = "high",
    @SerializedName("distance_km") val distanceKm: Double? = null
)

data class AreasResponse(
    @SerializedName("areas_checked") val areasChecked: Int = 0,
    @SerializedName("comfortable_areas") val comfortableAreas: List<AreaRow> = emptyList(),
    @SerializedName("stretch_areas") val stretchAreas: List<AreaRow> = emptyList(),
    @SerializedName("areas_out_of_reach") val areasOutOfReach: Int = 0,
    val near: String? = null,
    @SerializedName("max_km") val maxKm: Double? = null,
    val note: String? = null
)

enum class FairVerdict { BELOW, WITHIN, ABOVE, NO_VERDICT }

/** Pure logic for the Rent Assistant screens (no Android types, so it unit-tests on the JVM). */
object AreaAssistant {
    const val MIN_BUDGET = 3_000
    const val MAX_BUDGET = 2_000_000
    val DISTANCES_KM = listOf(2, 5, 10)
    const val DEFAULT_KM = 5
    const val MAX_BEDS_BATHS = 10

    /** "55,000", "KES 55000" or "55 000" -> 55000. Null if empty, not a number, or outside the allowed range. */
    fun parseBudget(text: String?): Int? {
        val digits = text.orEmpty().filter { it.isDigit() }
        if (digits.isEmpty() || digits.length > 8) return null
        val v = digits.toLong()
        return if (v in MIN_BUDGET..MAX_BUDGET) v.toInt() else null
    }

    /** Where the point estimate sits on the low..high bar, 0..1 (0.5 if the range is degenerate). */
    fun rangeFraction(low: Double, estimate: Double, high: Double): Double =
        if (high > low) ((estimate - low) / (high - low)).coerceIn(0.0, 1.0) else 0.5

    /** "low" and "none" confidence get a warning chip; "high" (or unknown) does not. */
    fun needsWarning(confidence: String?): Boolean = confidence == "low" || confidence == "none"

    /** Same rule as the check_listing_price tool: no verdict when there is no usable range or confidence is "none". */
    fun fairVerdict(asking: Double, low: Double?, high: Double?, confidence: String?): FairVerdict =
        when (RentRange.position(asking, low, high, confidence)) {
            RangePosition.ABOVE -> FairVerdict.ABOVE
            RangePosition.BELOW -> FairVerdict.BELOW
            RangePosition.WITHIN -> FairVerdict.WITHIN
            null -> FairVerdict.NO_VERDICT
        }

    /** Distance chip text: "0.8 km", "12 km". */
    fun formatKm(km: Double): String = if (km < 10) String.format(java.util.Locale.US, "%.1f km", km)
    else String.format(java.util.Locale.US, "%d km", Math.round(km))

    /**
     * Friendly text for a failed call. The server sends {"detail": "..."} with 422 (bad input,
     * message written for users) and 429 (busy). Anything else is a generic message.
     */
    fun errorMessage(code: Int, body: String?): String {
        val detail = runCatching {
            val el = JsonParser.parseString(body.orEmpty()).asJsonObject.get("detail")
            if (el != null && el.isJsonPrimitive) el.asString else null
        }.getOrNull()
        return when {
            code == 429 -> detail ?: "Busy right now. Please try again in a few seconds."
            code == 422 && !detail.isNullOrBlank() -> detail
            code == 422 -> "Those details were not accepted. Check the budget and areas and try again."
            code in 500..599 -> "The KodiWise service is busy or restarting. Please try again in a minute."
            else -> "Something went wrong (error $code). Please try again."
        }
    }

    /** True when an answer has nothing to show in either section. */
    fun isEmpty(r: AreasResponse): Boolean = r.comfortableAreas.isEmpty() && r.stretchAreas.isEmpty()
}
