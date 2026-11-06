package com.kodiwise.app

import android.app.Activity
import android.view.View
import android.widget.CheckBox
import android.widget.EditText
import android.widget.RadioGroup
import android.widget.TextView

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
        val hasGenerator: Int,
        val hasBorehole: Int,
        val hasCctv: Int,
        val hasDsq: Int,
        val hasPlayArea: Int,
        val hasGarden: Int
    )

    fun bindCollapse(activity: Activity) {
        val header = activity.findViewById<View>(R.id.headerAmenities)
        val body = activity.findViewById<View>(R.id.layoutAmenities)
        val arrow = activity.findViewById<TextView>(R.id.tvAmenitiesArrow)
        header.setOnClickListener {
            val expand = body.visibility != View.VISIBLE
            body.visibility = if (expand) View.VISIBLE else View.GONE
            arrow.text = if (expand) "▾" else "▸"
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
        val rgType = activity.findViewById<RadioGroup>(R.id.rgPropertyType)

        val sqM = if (cbDontKnow.isChecked) null else etSqm.text.toString().trim().toDoubleOrNull()

        val propertyType = when (rgType.checkedRadioButtonId) {
            R.id.rbApartment -> "apartment"
            R.id.rbHouse -> "house"
            R.id.rbBedsitter -> "bedsitter"
            else -> null
        }

        fun checked(id: Int): Int = if (activity.findViewById<CheckBox>(id).isChecked) 1 else 0

        return Values(
            sqM = sqM,
            isFurnished = checked(R.id.cbFurnished),
            propertyType = propertyType,
            hasGenerator = checked(R.id.cbGenerator),
            hasBorehole = checked(R.id.cbBorehole),
            hasCctv = checked(R.id.cbCctv),
            hasDsq = checked(R.id.cbDsq),
            hasPlayArea = checked(R.id.cbPlayArea),
            hasGarden = checked(R.id.cbGarden)
        )
    }
}
