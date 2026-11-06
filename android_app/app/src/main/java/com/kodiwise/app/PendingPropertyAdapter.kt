package com.kodiwise.app

import android.content.Context
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.TextView

class PendingPropertyAdapter(
    context: Context,
    private val items: List<PendingPropertyItem>,
    private val onApprove: (String) -> Unit,
    private val onReject: (String) -> Unit
) : ArrayAdapter<PendingPropertyItem>(context, 0, items) {

    override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
        val view = convertView ?: LayoutInflater.from(context)
            .inflate(R.layout.row_pending_property, parent, false)

        val item = items[position]

        view.findViewById<TextView>(R.id.tvTitle).text = item.title
        view.findViewById<TextView>(R.id.tvLoc).text = "Location: ${item.location}"
        view.findViewById<TextView>(R.id.tvRent).text = "Quoted: ${item.quotedRent}"

        view.findViewById<Button>(R.id.btnApprove).setOnClickListener { onApprove(item.id) }
        view.findViewById<Button>(R.id.btnReject).setOnClickListener { onReject(item.id) }

        return view
    }
}