package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import androidx.recyclerview.widget.RecyclerView
import coil.load

class ReviewImagesAdapter(
    private val items: MutableList<String>,
    private val onClick: ((String) -> Unit)? = null
) : RecyclerView.Adapter<ReviewImagesAdapter.VH>() {

    class VH(v: View) : RecyclerView.ViewHolder(v) {
        val img: ImageView = v.findViewById(R.id.imgThumb)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_review_image, parent, false)
        return VH(v)
    }

    override fun onBindViewHolder(h: VH, position: Int) {
        val url = items[position]

        h.img.load(url) {
            crossfade(true)
        }

        h.itemView.setOnClickListener {
            onClick?.invoke(url)
        }
    }

    override fun getItemCount(): Int = items.size

    fun replaceAll(newItems: List<String>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }
}