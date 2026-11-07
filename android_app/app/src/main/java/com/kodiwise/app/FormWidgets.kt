package com.kodiwise.app

import android.view.View
import android.widget.EditText

/** Small presentation helpers for form controls. */
object FormWidgets {

    /**
     * -/+ stepper around an existing number field. It only edits the field's
     * text; the screen still reads and validates that text exactly as before.
     */
    fun bindStepper(minus: View, field: EditText, plus: View, min: Int = 1, max: Int = 20) {
        fun current(): Int? = field.text.toString().trim().toIntOrNull()
        fun set(value: Int) {
            val v = value.coerceIn(min, max)
            field.setText(v.toString())
            field.setSelection(field.text.length)
        }
        minus.setOnClickListener { set((current() ?: min) - 1) }
        plus.setOnClickListener { set((current() ?: (min - 1)) + 1) }
    }
}
