package com.kodiwise.app

import kotlin.math.max
import kotlin.math.roundToInt

/** Pure rules for listing photos (no Android types, so they unit-test on the JVM). */
object PhotoRules {
    const val MAX_PHOTOS = 8
    const val MAX_LONG_SIDE = 1600
    const val TARGET_BYTES = 400 * 1024

    /** Hard ceiling, mirrors the 2 MB limit in storage.rules. */
    const val MAX_FILE_BYTES = 2 * 1024 * 1024

    /** JPEG qualities tried in order until the file is under TARGET_BYTES. */
    val QUALITY_STEPS = listOf(80, 72, 64, 56, 48, 40)

    /** Scales (w, h) down so the long side is at most [maxSide]; never upscales. */
    fun scaledSize(width: Int, height: Int, maxSide: Int = MAX_LONG_SIDE): Pair<Int, Int> {
        require(width > 0 && height > 0) { "image has no size" }
        val longSide = max(width, height)
        if (longSide <= maxSide) return width to height
        val f = maxSide.toDouble() / longSide
        return max(1, (width * f).roundToInt()) to max(1, (height * f).roundToInt())
    }

    /** Largest power-of-two decode sample that still leaves the long side >= [maxSide]. */
    fun sampleSize(width: Int, height: Int, maxSide: Int = MAX_LONG_SIDE): Int {
        var s = 1
        var longSide = max(width, height)
        while (longSide / 2 >= maxSide) {
            s *= 2
            longSide /= 2
        }
        return s
    }

    fun photoPath(propertyId: String, photoId: String): String =
        "properties/$propertyId/photos/$photoId.jpg"

    fun photosFolder(propertyId: String): String = "properties/$propertyId/photos"

    /** How many more photos can be added to a list that already holds [current]. */
    fun slotsLeft(current: Int): Int = (MAX_PHOTOS - current).coerceAtLeast(0)
}
