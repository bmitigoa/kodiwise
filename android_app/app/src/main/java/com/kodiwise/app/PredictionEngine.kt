package com.kodiwise.app

import kotlin.math.roundToInt

object PredictionEngine {

    /**
     * Demo predictor (stub).
     * Later we replace this logic with your trained ML model via API or on-device inference.
     */
    fun predictRent(
        location: String,
        bedrooms: Int,
        bathrooms: Int
    ): Int {
        val base = 15000

        val bedroomFactor = bedrooms * 8000
        val bathroomFactor = bathrooms * 5000

        val locationFactor = when (location.trim().lowercase()) {
            "kilimani" -> 20000
            "westlands" -> 22000
            "kileleshwa" -> 18000
            "lavington" -> 25000
            "ruaka" -> 12000
            "rongai" -> 8000
            "kasarani" -> 7000
            "embakasi" -> 6000
            else -> 5000
        }

        val predicted = base + bedroomFactor + bathroomFactor + locationFactor
        return (predicted / 100.0).roundToInt() * 100 // round to nearest 100
    }
}
