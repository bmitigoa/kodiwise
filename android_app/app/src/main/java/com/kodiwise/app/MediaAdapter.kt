package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import androidx.recyclerview.widget.RecyclerView
import coil.load

class MediaAdapter(
    private val items: MutableList<MediaItem>,
    private val onClick: (MediaItem) -> Unit
) : RecyclerView.Adapter<MediaAdapter.MediaVH>() {

    inner class MediaVH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val ivThumb: ImageView = itemView.findViewById(R.id.ivThumb)

        fun bind(item: MediaItem) {
            ivThumb.load(item.url) { crossfade(true) }

            // ✅ click on the whole item to avoid tiny tap area problems
            itemView.setOnClickListener {
                if (bindingAdapterPosition != RecyclerView.NO_POSITION) {
                    onClick(item)
                }
            }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): MediaVH {
        val v = LayoutInflater.from(parent.context).inflate(R.layout.item_media, parent, false)
        return MediaVH(v)
    }

    override fun onBindViewHolder(holder: MediaVH, position: Int) {
        holder.bind(items[position])
    }

    override fun getItemCount(): Int = items.size

    fun replaceAll(newItems: List<MediaItem>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }
}