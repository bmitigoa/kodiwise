package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import androidx.recyclerview.widget.RecyclerView
import coil.load

/** Thumbnails of the photos picked on the Add listing screen, each with a remove button. */
class PickedPhotosAdapter(
    private val items: MutableList<PendingPhoto>,
    private val onRemove: (PendingPhoto) -> Unit
) : RecyclerView.Adapter<PickedPhotosAdapter.VH>() {

    class VH(v: View) : RecyclerView.ViewHolder(v) {
        val img: ImageView = v.findViewById(R.id.ivPick)
        val remove: View = v.findViewById(R.id.btnRemovePick)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(LayoutInflater.from(parent.context).inflate(R.layout.item_pick_photo, parent, false))

    override fun onBindViewHolder(h: VH, position: Int) {
        val photo = items[position]
        h.img.load(photo.uri) { crossfade(true) }
        h.remove.setOnClickListener { onRemove(photo) }
    }

    override fun getItemCount(): Int = items.size

    fun add(newItems: List<PendingPhoto>) {
        val start = items.size
        items.addAll(newItems)
        notifyItemRangeInserted(start, newItems.size)
    }

    fun remove(photo: PendingPhoto) {
        val i = items.indexOfFirst { it.id == photo.id }
        if (i >= 0) {
            items.removeAt(i)
            notifyItemRemoved(i)
        }
    }
}
