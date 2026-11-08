package com.kodiwise.app

import android.app.Activity
import android.view.View
import android.widget.CheckBox
import android.widget.EditText
import com.google.android.material.chip.ChipGroup

/**
 * Shared binding for include_realistic_property_fields.xml, used by both
 * PredictionFormActivity and PropertyUploadActivity. Field names in
 * [Values] match ml.features.RUN_D_BINARY / the API's PredictRequest
 * exactly, so callers can serialize them directly without renaming.
 */
object RealisticPropertyFields {

    data class Values(
        val sqM: Double?,
        val isFurnished: Int,
        val propertyType: String?,
        // Amenities are null ("not given") when the section was never
        // expanded; 0/1 once the user opened it and so answered every box.
        val hasGenerator: Int?,
        val hasBorehole: Int?,
        val hasCctv: Int?,
        val hasDsq: Int?,
        val hasPlayArea: Int?,
        val hasGarden: Int?
    )

    /** null = section never opened (no answer); otherwise 1 if ticked, 0 if not. */
    fun amenityAnswer(sectionExpanded: Boolean, ticked: Boolean): Int? =
        if (!sectionExpanded) null else if (ticked) 1 else 0

    private const val AMENITIES_OPENED = "opened"

    /**
     * Fields saved on the property doc (same names as ml.features / the API schema).
     * Unanswered amenities and unknown size are saved as null, never as 0.
     */
    fun toFirestoreFields(v: Values): Map<String, Any?> = mapOf(
        "sq_m" to v.sqM,
        "is_furnished" to v.isFurnished,
        "is_apartment" to (if (v.propertyType == "apartment") 1 else 0),
        "is_house" to (if (v.propertyType == "house") 1 else 0),
        "is_bedsitter" to (if (v.propertyType == "bedsitter") 1 else 0),
        "has_generator" to v.hasGenerator,
        "has_borehole" to v.hasBorehole,
        "has_cctv" to v.hasCctv,
        "has_dsq" to v.hasDsq,
        "has_play_area" to v.hasPlayArea,
        "has_garden" to v.hasGarden
    )

    fun bindCollapse(activity: Activity) {
        val header = activity.findViewById<View>(R.id.headerAmenities)
        val body = activity.findViewById<View>(R.id.layoutAmenities)
        val chevron = activity.findViewById<View>(R.id.ivAmenitiesChevron)
        header.setOnClickListener {
            val expand = body.visibility != View.VISIBLE
            body.visibility = if (expand) View.VISIBLE else View.GONE
            if (expand) body.tag = AMENITIES_OPENED   // stays set even if collapsed again
            chevron.animate().rotation(if (expand) 180f else 0f).setDuration(150).start()
        }
    }

    fun bindDontKnowSize(activity: Activity) {
        val etSqm = activity.findViewById<EditText>(R.id.etSqm)
        val cbDontKnow = activity.findViewById<CheckBox>(R.id.cbDontKnowSize)
        cbDontKnow.setOnCheckedChangeListener { _, checked ->
            etSqm.isEnabled = !checked
            if (checked) etSqm.setText("")
        }
    }

    fun read(activity: Activity): Values {
        val etSqm = activity.findViewById<EditText>(R.id.etSqm)
        val cbDontKnow = activity.findViewById<CheckBox>(R.id.cbDontKnowSize)
        val rgType = activity.findViewById<ChipGroup>(R.id.rgPropertyType)

        val sqM = if (cbDontKnow.isChecked) null else etSqm.text.toString().trim().toDoubleOrNull()

        val propertyType = when (rgType.checkedChipId) {
            R.id.rbApartment -> "apartment"
            R.id.rbHouse -> "house"
            R.id.rbBedsitter -> "bedsitter"
            else -> null
        }

        fun checked(id: Int): Int = if (activity.findViewById<CheckBox>(id).isChecked) 1 else 0
        val expanded = activity.findViewById<View>(R.id.layoutAmenities).tag == AMENITIES_OPENED
        fun amenity(id: Int): Int? =
            amenityAnswer(expanded, activity.findViewById<CheckBox>(id).isChecked)

        return Values(
            sqM = sqM,
            isFurnished = checked(R.id.cbFurnished),
            propertyType = propertyType,
            hasGenerator = amenity(R.id.cbGenerator),
            hasBorehole = amenity(R.id.cbBorehole),
            hasCctv = amenity(R.id.cbCctv),
            hasDsq = amenity(R.id.cbDsq),
            hasPlayArea = amenity(R.id.cbPlayArea),
            hasGarden = amenity(R.id.cbGarden)
        )
    }
}
