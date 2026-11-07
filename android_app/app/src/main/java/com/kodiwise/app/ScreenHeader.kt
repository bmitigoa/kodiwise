package com.kodiwise.app

import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

object ScreenHeader {
    fun bind(activity: AppCompatActivity, title: String) {
        activity.findViewById<TextView?>(R.id.tvHeaderTitle)?.text = title
        activity.findViewById<View?>(R.id.btnBackHeader)?.setOnClickListener {
            activity.finish()
        }
    }
}