package com.kodiwise.app

import android.graphics.Rect
import android.view.View
import androidx.recyclerview.widget.RecyclerView

class GallerySpacingDecoration(private val spaceDp: Int) : RecyclerView.ItemDecoration() {

    private fun dp(view: View, value: Int): Int {
        return (value * view.resources.displayMetrics.density).toInt()
    }

    override fun getItemOffsets(
        outRect: Rect, view: View, parent: RecyclerView, state: RecyclerView.State
    ) {
        val spacePx = dp(view, spaceDp)
        outRect.right = spacePx
        if (parent.getChildAdapterPosition(view) == 0) outRect.left = spacePx
    }
}