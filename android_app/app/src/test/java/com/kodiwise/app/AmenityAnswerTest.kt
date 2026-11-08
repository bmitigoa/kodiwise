package com.kodiwise.app

import com.google.gson.Gson
import com.google.gson.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AmenityAnswerTest {
    private val amenityKeys = listOf(
        "has_generator", "has_borehole", "has_cctv", "has_dsq", "has_play_area", "has_garden", "has_backup_water"
    )

    private fun json(req: PredictionRequest): JsonObject = Gson().toJsonTree(req).asJsonObject

    private fun request(
        generator: Int?, borehole: Int?, cctv: Int?, dsq: Int?, play: Int?, garden: Int?
    ) = PredictionRequest(
        bedroomsNum = 2, bathroomsNum = 2, locationStd = "Kilimani",
        propertyTypeStd = "apartment", titleClean = "apartment in Kilimani",
        hasGenerator = generator, hasBorehole = borehole, hasCctv = cctv,
        hasDsq = dsq, hasPlayArea = play, hasGarden = garden
    )

    @Test fun neverExpandedMeansNoAnswerWhateverTheBoxesSay() {
        assertNull(RealisticPropertyFields.amenityAnswer(sectionExpanded = false, ticked = false))
        assertNull(RealisticPropertyFields.amenityAnswer(sectionExpanded = false, ticked = true))
    }

    @Test fun expandedMeansEveryBoxIsAnAnswer() {
        assertEquals(1, RealisticPropertyFields.amenityAnswer(sectionExpanded = true, ticked = true))
        assertEquals(0, RealisticPropertyFields.amenityAnswer(sectionExpanded = true, ticked = false))
    }

    @Test fun unansweredAmenitiesAreOmittedFromTheRequestJson() {
        val j = json(request(null, null, null, null, null, null))
        amenityKeys.forEach { assertFalse("$it must be omitted", j.has(it)) }
        assertTrue(j.has("is_furnished"))            // furnished is still always sent
        assertEquals(0, j.get("is_furnished").asInt)
    }

    @Test fun answeredAmenitiesAreSentAsZeroOrOne() {
        val j = json(request(1, 0, 0, 0, 0, 1))
        assertEquals(1, j.get("has_generator").asInt)
        assertEquals(0, j.get("has_borehole").asInt)
        assertEquals(1, j.get("has_garden").asInt)
    }
}
