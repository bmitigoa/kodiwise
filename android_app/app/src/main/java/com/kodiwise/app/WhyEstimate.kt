package com.kodiwise.app

import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToLong

/** Pure helpers for the "Why this estimate" card (unit-tested). */
object WhyEstimate {

    const val MAX_ROWS = 5

    /** Rounded to the nearest KES 500 so it reads as approximate: "+KES 15,000" / "-KES 4,500". */
    fun formatEffect(effectKes: Double): String {
        val rounded = (abs(effectKes) / 500.0).roundToLong() * 500
        val sign = if (effectKes < 0) "-" else "+"
        return sign + "KES " + String.format(Locale.US, "%,d", rounded)
    }

    /** Baseline shown to the nearest KES 1,000 ("KES 59,000"). */
    fun formatBaseline(kes: Double): String {
        val rounded = (kes / 1000.0).roundToLong() * 1000
        return "KES " + String.format(Locale.US, "%,d", rounded)
    }

    /** Up to 5 factors, largest effect first, ignoring ones that round to nothing. */
    fun visible(factors: List<ExplanationFactor>): List<ExplanationFactor> =
        factors.filter { abs(it.effectKes) >= 250.0 }
            .sortedByDescending { abs(it.effectKes) }
            .take(MAX_ROWS)

    /** Bar length per factor as a share of the largest one (min 0.08 so small ones stay visible). */
    fun barFractions(factors: List<ExplanationFactor>): List<Float> {
        val max = factors.maxOfOrNull { abs(it.effectKes) } ?: return emptyList()
        if (max <= 0.0) return factors.map { 0.08f }
        return factors.map { (abs(it.effectKes) / max).toFloat().coerceIn(0.08f, 1f) }
    }

    fun isUp(f: ExplanationFactor): Boolean = f.effectKes >= 0

    fun describe(f: ExplanationFactor): String =
        "${f.label}, ${if (isUp(f)) "raises" else "lowers"} the estimate by about " +
            formatEffect(f.effectKes).drop(1)
}
