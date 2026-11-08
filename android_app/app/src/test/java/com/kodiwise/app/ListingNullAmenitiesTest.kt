package com.kodiwise.app

import com.google.firebase.firestore.util.CustomClassMapper
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A listing saved with unanswered amenities (null) must load through the same
 * Firestore -> Property mapping every list/detail/admin screen uses, without
 * crashing, and nothing in the app may turn null into "No".
 */
class ListingNullAmenitiesTest {

    private val unanswered = RealisticPropertyFields.Values(
        sqM = null, isFurnished = 0, propertyType = null,
        hasGenerator = null, hasBorehole = null, hasCctv = null,
        hasDsq = null, hasPlayArea = null, hasGarden = null
    )

    /** What PropertyUploadActivity writes, minus server timestamps. */
    private fun savedDoc(realistic: RealisticPropertyFields.Values): Map<String, Any?> =
        mapOf(
            "title" to "2bdrm in Kilimani", "locationName" to "Kilimani",
            "bedrooms" to 2, "bathrooms" to 2, "quotedRent" to 80000,
            "description" to "", "status" to "approved", "ownerId" to "u1",
            "predictedRent" to 87000.0, "predictedLow" to null, "predictedHigh" to null,
            "locationConfidence" to null, "rentBand" to "FAIR", "rentRatio" to 0.9,
            "arScale" to 0.4, "arRotationY" to 180
        ) + RealisticPropertyFields.toFirestoreFields(realistic)

    private fun load(doc: Map<String, Any?>): Property =
        CustomClassMapper.convertToCustomClass(doc, Property::class.java, null)

    @Test fun unansweredAmenitiesAreSavedAsNullNotZero() {
        val f = RealisticPropertyFields.toFirestoreFields(unanswered)
        listOf("has_generator", "has_borehole", "has_cctv", "has_dsq", "has_play_area", "has_garden")
            .forEach { assertTrue("$it must be present and null", f.containsKey(it) && f[it] == null) }
        assertNull(f["sq_m"])
        assertEquals(0, f["is_furnished"])      // furnished is an answer (visible checkbox)
    }

    @Test fun answeredAmenitiesAreSavedAsZeroOrOne() {
        val f = RealisticPropertyFields.toFirestoreFields(
            unanswered.copy(hasGenerator = 1, hasBorehole = 0, hasCctv = 0, hasDsq = 0, hasPlayArea = 0, hasGarden = 1)
        )
        assertEquals(1, f["has_generator"])
        assertEquals(0, f["has_borehole"])
        assertEquals(1, f["has_garden"])
    }

    @Test fun listingWithNullAmenitiesLoadsIntoProperty() {
        val p = load(savedDoc(unanswered))
        assertEquals("Kilimani", p.location)
        assertEquals(2, p.bedrooms)
        assertEquals(80000, p.price)
        assertNull(p.sqM)                        // size chip is hidden for null
        assertNull(p.predictedLow)
        assertNull(p.predictedHigh)
        assertNull(p.locationConfidence)
    }

    @Test fun listingWithAnsweredAmenitiesAndSizeStillLoads() {
        val p = load(savedDoc(unanswered.copy(sqM = 90.0, hasCctv = 1, hasGarden = 0)))
        assertEquals(90.0, p.sqM!!, 1e-9)
    }

    @Test fun propertyModelDoesNotCarryAmenities() {
        // No screen reads amenity fields, so there is no place a null could be
        // rendered as "No". If one is ever added it must handle null.
        val names = Property::class.java.declaredFields.map { it.name.lowercase() }
        assertTrue(names.none { it.startsWith("has") || it.contains("furnish") || it.contains("amenit") })
    }
}
