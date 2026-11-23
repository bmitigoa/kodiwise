package com.kodiwise.app

import android.content.res.ColorStateList
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.TextViewCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Rent Assistant, step 3: areas that fit the budget, as "Comfortable" and
 * "Stretch" cards. Tap a card for the full estimate with "Why this estimate".
 */
class AreaResultsActivity : AppCompatActivity() {

    private var budget = 0
    private var beds = 1
    private var baths = 1
    private var near: String? = null
    private var km = AreaAssistant.DEFAULT_KM
    private var opening = false

    private lateinit var progress: View
    private lateinit var groupError: View
    private lateinit var groupEmpty: View
    private lateinit var groupResults: View
    private lateinit var tvError: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!AuthManager.isLoggedIn()) {
            finish()
            return
        }
        setContentView(R.layout.activity_area_results)
        ScreenHeader.bind(this, getString(R.string.title_area_results))

        budget = intent.getIntExtra(EXTRA_BUDGET, 0)
        beds = intent.getIntExtra(EXTRA_BEDS, 1)
        baths = intent.getIntExtra(EXTRA_BATHS, 1)
        near = intent.getStringExtra(EXTRA_NEAR)
        km = intent.getIntExtra(EXTRA_KM, AreaAssistant.DEFAULT_KM)

        progress = findViewById(R.id.progressResults)
        groupError = findViewById(R.id.groupError)
        groupEmpty = findViewById(R.id.groupEmpty)
        groupResults = findViewById(R.id.groupResults)
        tvError = findViewById(R.id.tvError)

        findViewById<TextView>(R.id.tvStepLabel).text = getString(R.string.finder_step, 3)
        findViewById<TextView>(R.id.tvSummary).text = getString(
            R.string.results_summary_beds_baths,
            "${ListingCard.formatKes(budget)} / month",
            "${resources.getQuantityString(R.plurals.beds, beds, beds)}, " +
                resources.getQuantityString(R.plurals.baths, baths, baths)
        )
        near?.let {
            findViewById<TextView>(R.id.tvSummaryNear).apply {
                text = getString(R.string.results_near, it, km)
                visibility = View.VISIBLE
            }
        }

        findViewById<View>(R.id.btnFair).setOnClickListener { FairRentSheet.show(this, beds, baths) }
        findViewById<View>(R.id.btnRetry).setOnClickListener { load() }
        findViewById<View>(R.id.btnEditSearch).setOnClickListener { finish() }
        findViewById<View>(R.id.btnEmptyEdit).setOnClickListener { finish() }

        load()
    }

    private fun load() {
        progress.visibility = View.VISIBLE
        groupError.visibility = View.GONE
        groupEmpty.visibility = View.GONE
        groupResults.visibility = View.GONE
        lifecycleScope.launch {
            try {
                val resp = withContext(Dispatchers.IO) {
                    ApiClient.api.areasWithinBudget(budget, beds, baths, near, near?.let { km.toDouble() })
                }
                val body = resp.body()
                if (resp.isSuccessful && body != null) {
                    show(body)
                } else {
                    showError(AreaAssistant.errorMessage(resp.code(), resp.errorBody()?.string()))
                }
            } catch (e: Exception) {
                showError(EstimateLauncher.NETWORK_ERROR)
            }
        }
    }

    private fun showError(message: String) {
        progress.visibility = View.GONE
        tvError.text = message
        groupError.visibility = View.VISIBLE
    }

    private fun show(r: AreasResponse) {
        progress.visibility = View.GONE
        if (AreaAssistant.isEmpty(r)) {
            groupEmpty.visibility = View.VISIBLE
            return
        }
        fill(R.id.tvComfortableTitle, R.id.tvComfortableSub, R.id.listComfortable, r.comfortableAreas)
        fill(R.id.tvStretchTitle, R.id.tvStretchSub, R.id.listStretch, r.stretchAreas)
        findViewById<TextView>(R.id.tvOutOfReach).apply {
            if (r.areasOutOfReach > 0) {
                text = getString(R.string.results_out_of_reach, r.areasOutOfReach)
                visibility = View.VISIBLE
            } else {
                visibility = View.GONE
            }
        }
        groupResults.visibility = View.VISIBLE
    }

    private fun fill(titleId: Int, subId: Int, listId: Int, rows: List<AreaRow>) {
        val list = findViewById<LinearLayout>(listId)
        list.removeAllViews()
        val vis = if (rows.isEmpty()) View.GONE else View.VISIBLE
        findViewById<View>(titleId).visibility = vis
        findViewById<View>(subId).visibility = vis
        rows.forEach { list.addView(card(list, it)) }
    }

    private fun card(parent: LinearLayout, row: AreaRow): View {
        val v = LayoutInflater.from(this).inflate(R.layout.item_area_card, parent, false)
        v.findViewById<TextView>(R.id.tvAreaName).text = row.area
        v.findViewById<TextView>(R.id.tvAreaEstimate).text =
            getString(R.string.listing_price_month, ListingCard.formatKes(row.estimateKes))
        v.findViewById<TextView>(R.id.tvAreaLow).text = ListingCard.formatKes(row.rangeLowKes)
        v.findViewById<TextView>(R.id.tvAreaHigh).text = ListingCard.formatKes(row.rangeHighKes)

        row.distanceKm?.let { d ->
            v.findViewById<TextView>(R.id.tvAreaDistance).apply {
                text = AreaAssistant.formatKm(d)
                backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(context, R.color.kw_primary_container))
                setTextColor(ContextCompat.getColor(context, R.color.kw_on_primary_container))
                visibility = View.VISIBLE
            }
        }

        if (AreaAssistant.needsWarning(row.locationConfidence)) {
            val low = row.locationConfidence == "low"
            val chip = v.findViewById<TextView>(R.id.tvAreaConfidence)
            val fg = ColorStateList.valueOf(
                ContextCompat.getColor(this, if (low) R.color.kw_on_secondary_container else R.color.kw_on_neutral_chip)
            )
            chip.setText(if (low) R.string.area_rough else R.string.area_no_data)
            chip.backgroundTintList = ColorStateList.valueOf(
                ContextCompat.getColor(this, if (low) R.color.kw_secondary_container else R.color.kw_neutral_chip)
            )
            chip.setTextColor(fg)
            TextViewCompat.setCompoundDrawableTintList(chip, fg)
            chip.visibility = View.VISIBLE
        }

        val bar = v.findViewById<View>(R.id.areaRangeBar)
        val marker = v.findViewById<View>(R.id.areaRangeMarker)
        val fraction = AreaAssistant.rangeFraction(row.rangeLowKes, row.estimateKes, row.rangeHighKes)
        bar.post {
            val x = ((bar.width - marker.width) * fraction).toFloat()
            marker.translationX = if (bar.layoutDirection == View.LAYOUT_DIRECTION_RTL) -x else x
        }
        bar.contentDescription = getString(
            R.string.cd_area_range, ListingCard.formatKes(row.rangeLowKes), ListingCard.formatKes(row.rangeHighKes)
        )

        v.setOnClickListener { openEstimate(row.area) }
        return v
    }

    private fun openEstimate(area: String) {
        if (opening) return
        opening = true
        progress.visibility = View.VISIBLE
        lifecycleScope.launch {
            val error = EstimateLauncher.open(this@AreaResultsActivity, area, beds, baths)
            progress.visibility = View.GONE
            opening = false
            if (error != null) Toast.makeText(this@AreaResultsActivity, error, Toast.LENGTH_LONG).show()
        }
    }

    companion object {
        const val EXTRA_BUDGET = "budget"
        const val EXTRA_BEDS = "beds"
        const val EXTRA_BATHS = "baths"
        const val EXTRA_NEAR = "near"
        const val EXTRA_KM = "km"
    }
}
