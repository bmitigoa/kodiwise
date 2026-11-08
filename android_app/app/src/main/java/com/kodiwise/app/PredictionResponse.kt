package com.kodiwise.app

import com.google.gson.annotations.SerializedName

data class PredictionResponse(

    @SerializedName("predicted_rent_kes")
    val predictedRentKes: Double? = null,

    // Only populated by the new KodiWise API (ml.features.APP_FEATURE_SET /
    // Run C). Nullable so the app still works against the old deployed v8
    // API, which doesn't return a range -- see docs/PROGRESS.md.
    @SerializedName("predicted_rent_low_kes")
    val predictedRentLowKes: Double? = null,

    @SerializedName("predicted_rent_high_kes")
    val predictedRentHighKes: Double? = null,

    @SerializedName("model_version")
    val modelVersion: String? = null,

    // Null against the old v8 API (no such concept there). When present
    // and false, the typed location didn't match any known neighbourhood
    // (or alias) and the estimate fell back to the Nairobi-wide average.
    @SerializedName("location_recognised")
    val locationRecognised: Boolean? = null,

    // "high" | "low" | "none" -- how much training data backs the matched
    // neighbourhood. Null against API versions that predate the field;
    // treated the same as "high" (no hint shown).
    @SerializedName("location_confidence")
    val locationConfidence: String? = null,

    val note: String? = null,

    // Null when the server predates explanations or explain=false.
    val explanation: Explanation? = null
) {

    fun bestValue(): Double {
        return predictedRentKes ?: 0.0
    }

    fun hasRange(): Boolean {
        return predictedRentLowKes != null && predictedRentHighKes != null
    }

    companion object {
        /** Hint for the result screen, or null when no note is needed
         *  ("high", missing, or an unexpected value from a newer API). */
        fun locationConfidenceHint(confidence: String?): String? = when (confidence) {
            "low" -> "Few listings in this area. Treat this estimate as rough."
            "none" -> "Not enough local data. This estimate is based mostly on the Nairobi average."
            else -> null
        }
    }
}

/** "Why this estimate": approximate KES effects per factor, from /predict. */
data class Explanation(
    @SerializedName("baseline_rent_kes") val baselineRentKes: Double? = null,
    val factors: List<ExplanationFactor> = emptyList(),
    val note: String? = null
)

data class ExplanationFactor(
    val name: String = "",
    val label: String = "",
    val direction: String = "+",
    @SerializedName("effect_kes") val effectKes: Double = 0.0
)
