package com.kodiwise.app

import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AreaAssistantTest {

    @Test fun budgetParsingAcceptsCommonFormats() {
        assertEquals(55000, AreaAssistant.parseBudget("55000"))
        assertEquals(55000, AreaAssistant.parseBudget("55,000"))
        assertEquals(55000, AreaAssistant.parseBudget(" KES 55 000 "))
        assertEquals(3000, AreaAssistant.parseBudget("3000"))
        assertEquals(2_000_000, AreaAssistant.parseBudget("2,000,000"))
    }

    @Test fun budgetParsingRejectsBadValues() {
        assertNull(AreaAssistant.parseBudget(null))
        assertNull(AreaAssistant.parseBudget(""))
        assertNull(AreaAssistant.parseBudget("abc"))
        assertNull(AreaAssistant.parseBudget("2999"))
        assertNull(AreaAssistant.parseBudget("2000001"))
        assertNull(AreaAssistant.parseBudget("123456789012"))
    }

    @Test fun rangeFractionPlacesTheMarker() {
        assertEquals(0.5, AreaAssistant.rangeFraction(40.0, 60.0, 80.0), 1e-9)
        assertEquals(0.0, AreaAssistant.rangeFraction(40.0, 30.0, 80.0), 1e-9)
        assertEquals(1.0, AreaAssistant.rangeFraction(40.0, 99.0, 80.0), 1e-9)
        assertEquals(0.5, AreaAssistant.rangeFraction(50.0, 50.0, 50.0), 1e-9)
    }

    @Test fun onlyLowAndNoneConfidenceGetAWarning() {
        assertTrue(AreaAssistant.needsWarning("low"))
        assertTrue(AreaAssistant.needsWarning("none"))
        assertFalse(AreaAssistant.needsWarning("high"))
        assertFalse(AreaAssistant.needsWarning(null))
    }

    @Test fun fairVerdictMatchesTheCheckListingPriceRule() {
        assertEquals(FairVerdict.WITHIN, AreaAssistant.fairVerdict(60000.0, 45000.0, 80000.0, "high"))
        assertEquals(FairVerdict.ABOVE, AreaAssistant.fairVerdict(90000.0, 45000.0, 80000.0, "high"))
        assertEquals(FairVerdict.BELOW, AreaAssistant.fairVerdict(30000.0, 45000.0, 80000.0, "low"))
        // edges are within
        assertEquals(FairVerdict.WITHIN, AreaAssistant.fairVerdict(45000.0, 45000.0, 80000.0, "high"))
        assertEquals(FairVerdict.WITHIN, AreaAssistant.fairVerdict(80000.0, 45000.0, 80000.0, "high"))
        // too little local data, or no usable range: no verdict
        assertEquals(FairVerdict.NO_VERDICT, AreaAssistant.fairVerdict(60000.0, 45000.0, 80000.0, "none"))
        assertEquals(FairVerdict.NO_VERDICT, AreaAssistant.fairVerdict(60000.0, null, 80000.0, "high"))
        assertEquals(FairVerdict.NO_VERDICT, AreaAssistant.fairVerdict(60000.0, 80000.0, 45000.0, "high"))
    }

    @Test fun distancesAreFormatted() {
        assertEquals("0.8 km", AreaAssistant.formatKm(0.84))
        assertEquals("3.2 km", AreaAssistant.formatKm(3.2))
        assertEquals("12 km", AreaAssistant.formatKm(11.6))
    }

    @Test fun serverMessagesAreShownForBadInputAndBusy() {
        assertEquals("Unknown area Atlantis.", AreaAssistant.errorMessage(422, """{"detail":"Unknown area Atlantis."}"""))
        assertTrue(AreaAssistant.errorMessage(429, """{"detail":"Busy right now. Please try again in a few seconds."}""")
            .startsWith("Busy right now"))
    }

    @Test fun otherFailuresGetFriendlyGenericMessages() {
        // FastAPI validation errors send a list in "detail": do not show raw JSON
        val generic = AreaAssistant.errorMessage(422, """{"detail":[{"loc":["query","bedrooms"],"msg":"bad"}]}""")
        assertFalse(generic.contains("loc"))
        assertTrue(AreaAssistant.errorMessage(503, "<html>").contains("try again", ignoreCase = true))
        assertTrue(AreaAssistant.errorMessage(404, null).contains("404"))
        assertTrue(AreaAssistant.errorMessage(429, null).contains("try again", ignoreCase = true))
    }

    @Test fun responseParsesFromTheApiJson() {
        val json = """
            {"areas_checked": 5, "areas_out_of_reach": 2, "near": "Kilimani", "max_km": 5.0, "note": "Estimate only.",
             "comfortable_areas": [{"area": "Kilimani", "estimate_kes": 55000, "range_low_kes": 40000,
                "range_high_kes": 70000, "location_confidence": "low", "distance_km": 0.0, "why": null}],
             "stretch_areas": [{"area": "Lavington", "estimate_kes": 65000, "range_low_kes": 50000,
                "range_high_kes": 85000, "location_confidence": "high"}]}
        """.trimIndent()
        val r = Gson().fromJson(json, AreasResponse::class.java)
        assertEquals(5, r.areasChecked)
        assertEquals(2, r.areasOutOfReach)
        assertEquals("Kilimani", r.near)
        assertEquals("low", r.comfortableAreas.single().locationConfidence)
        assertEquals(0.0, r.comfortableAreas.single().distanceKm!!, 0.0)
        assertNull(r.stretchAreas.single().distanceKm)
        assertFalse(AreaAssistant.isEmpty(r))
    }

    @Test fun emptyAnswerIsDetected() {
        val r = Gson().fromJson("""{"areas_checked": 32, "areas_out_of_reach": 32,
            "comfortable_areas": [], "stretch_areas": []}""", AreasResponse::class.java)
        assertTrue(AreaAssistant.isEmpty(r))
        assertTrue(AreaAssistant.isEmpty(AreasResponse()))
    }

    @Test fun distanceChoicesMatchTheSpec() {
        assertEquals(listOf(2, 5, 10), AreaAssistant.DISTANCES_KM)
        assertTrue(AreaAssistant.DEFAULT_KM in AreaAssistant.DISTANCES_KM)
    }
}
