package com.kodiwise.app

import com.google.gson.annotations.SerializedName

data class PredictionResponse(

    @SerializedName("predicted_rent_kes")
    val predictedRentKes: Double? = null,

    val note: String? = null
) {

    fun bestValue(): Double {
        return predictedRentKes ?: 0.0
    }
}