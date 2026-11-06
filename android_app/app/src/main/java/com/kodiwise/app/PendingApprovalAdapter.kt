package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.widget.AppCompatButton
import androidx.recyclerview.widget.RecyclerView
import coil.load

class PendingApprovalAdapter(
    private val items: MutableList<Property>,
    private val onReview: (Property) -> Unit
) : RecyclerView.Adapter<PendingApprovalAdapter.VH>() {

    inner class VH(v: View) : RecyclerView.ViewHolder(v) {
        val ivCover: ImageView = v.findViewById(R.id.ivCover)
        val tvTitle: TextView = v.findViewById(R.id.tvTitle)
        val tvLocation: TextView = v.findViewById(R.id.tvLocation)
        val tvMeta: TextView = v.findViewById(R.id.tvMeta)
        val tvStatus: TextView = v.findViewById(R.id.tvStatus)
        val btnReview: AppCompatButton = v.findViewById(R.id.btnReview)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_pending_property, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]

        holder.tvTitle.text = item.title.ifBlank { "Untitled Property" }
        holder.tvLocation.text = item.location.ifBlank { "-" }
        holder.tvMeta.text = "${item.bedrooms} Bedrooms • ${item.bathrooms} Bathrooms • KES ${item.price}"
        holder.tvStatus.text = item.prettyStatus().uppercase()

        val imageUrl = when {
            item.coverImageUrl.isNotBlank() -> item.coverImageUrl
            item.imageUrls.isNotEmpty() -> item.imageUrls.first()
            else -> ""
        }

        if (imageUrl.isNotBlank()) {
            holder.ivCover.load(imageUrl) {
                crossfade(true)
            }
        } else {
            holder.ivCover.setImageResource(android.R.color.darker_gray)
        }

        holder.btnReview.setOnClickListener {
            onReview(item)
        }

        holder.itemView.setOnClickListener {
            onReview(item)
        }
    }

    override fun getItemCount(): Int = items.size

    fun replaceAll(newItems: List<Property>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }
}