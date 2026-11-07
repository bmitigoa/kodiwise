package com.kodiwise.app

/**
 * Where a listing's quoted rent sits relative to the model's prediction
 * range (10th-90th percentile band returned by /predict and saved with the
 * listing as predictedLow / predictedHigh). Replaces the old fixed-percentage
 * rentBand for display.
 */
enum class RangePosition { BELOW, WITHIN, ABOVE }

object RentRange {

    /**
     * @return null when no badge should be shown: the listing has no saved
     *   range (older listings), the range is invalid, or the location had too
     *   little training data ("none" confidence) for the range to mean much.
     */
    fun position(quoted: Double, low: Double?, high: Double?, locationConfidence: String?): RangePosition? {
        if (low == null || high == null) return null
        if (low <= 0.0 || high < low || quoted <= 0.0) return null
        if (locationConfidence == "none") return null
        return when {
            quoted > high -> RangePosition.ABOVE
            quoted < low -> RangePosition.BELOW
            else -> RangePosition.WITHIN
        }
    }
}
