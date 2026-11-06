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

    val note: String? = null
) {

    fun bestValue(): Double {
        return predictedRentKes ?: 0.0
    }

    fun hasRange(): Boolean {
        return predictedRentLowKes != null && predictedRentHighKes != null
    }
}