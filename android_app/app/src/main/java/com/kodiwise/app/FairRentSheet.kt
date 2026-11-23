package com.kodiwise.app

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.View
import android.widget.EditText
import android.widget.TextView
import androidx.annotation.ColorRes
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.TextViewCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.MaterialAutoCompleteTextView
import com.google.android.material.textfield.TextInputLayout
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * "Is this rent fair?": the asking rent is compared with the estimated range,
 * using the same rule as the check_listing_price tool (within / above / below,
 * or no verdict when local data is too thin).
 */
object FairRentSheet {

    fun show(activity: AppCompatActivity, defaultBeds: Int = 1, defaultBaths: Int = 1, defaultArea: String? = null) {
        val dialog = BottomSheetDialog(activity)
        val v = LayoutInflater.from(activity).inflate(R.layout.sheet_fair_rent, null)
        dialog.setContentView(v)

        val tilArea = v.findViewById<TextInputLayout>(R.id.tilFairArea)
        val etArea = v.findViewById<MaterialAutoCompleteTextView>(R.id.etFairArea)
        val etBeds = v.findViewById<EditText>(R.id.etFairBeds)
        val etBaths = v.findViewById<EditText>(R.id.etFairBaths)
        val tilRent = v.findViewById<TextInputLayout>(R.id.tilFairRent)
        val etRent = v.findViewById<EditText>(R.id.etFairRent)
        val progress = v.findViewById<View>(R.id.progressFair)
        val verdict = v.findViewById<TextView>(R.id.tvFairVerdict)
        val note = v.findViewById<View>(R.id.tvFairNote)
        val btn = v.findViewById<MaterialButton>(R.id.btnFairCheck)

        etBeds.setText(defaultBeds.toString())
        etBaths.setText(defaultBaths.toString())
        defaultArea?.let { etArea.setText(it) }
        FormWidgets.bindStepper(v.findViewById(R.id.btnFairBedsMinus), etBeds, v.findViewById(R.id.btnFairBedsPlus),
            min = 0, max = AreaAssistant.MAX_BEDS_BATHS)
        FormWidgets.bindStepper(v.findViewById(R.id.btnFairBathsMinus), etBaths, v.findViewById(R.id.btnFairBathsPlus),
            min = 0, max = AreaAssistant.MAX_BEDS_BATHS)

        val adapter = android.widget.ArrayAdapter(
            activity, android.R.layout.simple_dropdown_item_1line, LocationDirectory.getCached(activity).toMutableList()
        )
        etArea.setAdapter(adapter)
        etArea.doAfterTextChanged { tilArea.error = null }
        etRent.doAfterTextChanged { tilRent.error = null }

        btn.setOnClickListener {
            val area = LocationDirectory.match(etArea.text.toString(), LocationDirectory.getCached(activity))
            if (area == null) {
                tilArea.error = activity.getString(R.string.fair_pick_area)
                return@setOnClickListener
            }
            val asking = AreaAssistant.parseBudget(etRent.text.toString())
            if (asking == null) {
                tilRent.error = activity.getString(R.string.fair_enter_rent)
                return@setOnClickListener
            }
            val beds = (etBeds.text.toString().toIntOrNull() ?: 1).coerceIn(0, AreaAssistant.MAX_BEDS_BATHS)
            val baths = (etBaths.text.toString().toIntOrNull() ?: 1).coerceIn(0, AreaAssistant.MAX_BEDS_BATHS)

            btn.isEnabled = false
            progress.visibility = View.VISIBLE
            verdict.visibility = View.GONE
            note.visibility = View.GONE
            activity.lifecycleScope.launch {
                try {
                    val resp = withContext(Dispatchers.IO) {
                        ApiClient.api.predict(EstimateLauncher.request(area, beds, baths))
                    }
                    val body = resp.body()
                    if (!resp.isSuccessful || body == null || !body.hasRange()) {
                        show(verdict, note, AreaAssistant.errorMessage(resp.code(), resp.errorBody()?.string()), null)
                    } else {
                        val low = body.predictedRentLowKes!!
                        val high = body.predictedRentHighKes!!
                        val kind = AreaAssistant.fairVerdict(asking.toDouble(), low, high, body.locationConfidence)
                        val range = "${ListingCard.formatKes(low)} to ${ListingCard.formatKes(high)}"
                        val text = activity.getString(
                            when (kind) {
                                FairVerdict.WITHIN -> R.string.fair_within
                                FairVerdict.ABOVE -> R.string.fair_above
                                FairVerdict.BELOW -> R.string.fair_below
                                FairVerdict.NO_VERDICT -> R.string.fair_no_verdict
                            }, range
                        )
                        show(verdict, note, text, kind)
                    }
                } catch (e: Exception) {
                    show(verdict, note, EstimateLauncher.NETWORK_ERROR, null)
                } finally {
                    progress.visibility = View.GONE
                    btn.isEnabled = true
                }
            }
        }
        dialog.show()
    }

    private fun show(tv: TextView, note: View, text: String, kind: FairVerdict?) {
        @ColorRes val bg: Int
        @ColorRes val fg: Int
        when (kind) {
            FairVerdict.WITHIN -> { bg = R.color.kw_primary_container; fg = R.color.kw_on_primary_container }
            FairVerdict.ABOVE -> { bg = R.color.kw_error_container; fg = R.color.kw_on_error_container }
            FairVerdict.BELOW -> { bg = R.color.kw_tertiary_container; fg = R.color.kw_on_tertiary_container }
            else -> { bg = R.color.kw_neutral_chip; fg = R.color.kw_on_neutral_chip }
        }
        val ctx = tv.context
        val fgList = ColorStateList.valueOf(ContextCompat.getColor(ctx, fg))
        tv.text = text
        tv.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(ctx, bg))
        tv.setTextColor(fgList)
        TextViewCompat.setCompoundDrawableTintList(tv, fgList)
        tv.visibility = View.VISIBLE
        note.visibility = if (kind == null) View.GONE else View.VISIBLE
    }

    private fun EditText.doAfterTextChanged(action: () -> Unit) {
        addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: android.text.Editable?) = action()
        })
    }
}
