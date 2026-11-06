package com.kodiwise.app

import android.widget.ImageButton
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

object ScreenHeader {
    fun bind(activity: AppCompatActivity, title: String) {
        activity.findViewById<TextView?>(R.id.tvHeaderTitle)?.text = title
        activity.findViewById<ImageButton?>(R.id.btnBackHeader)?.setOnClickListener {
            activity.finish()
        }
    }
}