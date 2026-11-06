package com.kodiwise.app

import com.google.firebase.firestore.PropertyName

data class Property(
    var id: String = "",

    var title: String = "",

    @get:PropertyName("locationName")
    @set:PropertyName("locationName")
    var location: String = "",

    var bedrooms: Int = 0,
    var bathrooms: Int = 0,

    @get:PropertyName("quotedRent")
    @set:PropertyName("quotedRent")
    var price: Int = 0,

    var description: String = "",

    var coverImageUrl: String = "",

    // Optional (if you later decide to save imageUrls directly on property doc)
    var imageUrls: List<String> = emptyList(),

    // ✅ Admin review comment saved on the property doc as: adminNotes
    var adminNotes: String = "",

    var status: String = "pending",

    var rentBand: String = "FAIR",
    var predictedRent: Double = 0.0,
    var rentRatio: Double = 1.0,

    var ownerId: String = "",
    var createdAt: Any? = null,

    var modelKey: String = ""
) {
    fun prettyStatus(): String {
        val s = status.trim()
        if (s.isEmpty()) return "Pending"
        return s.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
    }
}