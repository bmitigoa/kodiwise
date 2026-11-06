package com.kodiwise.app

import android.os.Bundle
import android.os.Environment
import android.util.Log
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

data class PerfResult(
    val operation: String,
    val run: Int,
    val durationMs: Long,
    val timestamp: String
)

class PerformanceTestActivity : AppCompatActivity() {

    private val firestore by lazy { FirebaseFirestore.getInstance() }

    private lateinit var etRuns: EditText
    private lateinit var btnPredictionTest: Button
    private lateinit var btnFirestoreSaveTest: Button
    private lateinit var btnFirestoreReadTest: Button
    private lateinit var btnExportCsv: Button
    private lateinit var btnClearResults: Button
    private lateinit var tvResults: TextView
    private lateinit var progressBar: ProgressBar

    private val results = mutableListOf<PerfResult>()
    private var lastSavedPerfDocId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_performance_test)

        etRuns = findViewById(R.id.etRuns)
        btnPredictionTest = findViewById(R.id.btnPredictionTest)
        btnFirestoreSaveTest = findViewById(R.id.btnFirestoreSaveTest)
        btnFirestoreReadTest = findViewById(R.id.btnFirestoreReadTest)
        btnExportCsv = findViewById(R.id.btnExportCsv)
        btnClearResults = findViewById(R.id.btnClearResults)
        tvResults = findViewById(R.id.tvResults)
        progressBar = findViewById(R.id.progressBar)

        btnPredictionTest.setOnClickListener {
            runPredictionTests(getRuns())
        }

        btnFirestoreSaveTest.setOnClickListener {
            runFirestoreSaveTests(getRuns())
        }

        btnFirestoreReadTest.setOnClickListener {
            runFirestoreReadTests(getRuns())
        }

        btnExportCsv.setOnClickListener {
            exportResultsToCsv()
        }

        btnClearResults.setOnClickListener {
            results.clear()
            tvResults.text = "Results cleared."
            toast("Results cleared")
        }
    }

    private fun getRuns(): Int {
        return etRuns.text.toString().trim().toIntOrNull()?.coerceAtLeast(1) ?: 5
    }

    private fun setBusy(isBusy: Boolean) {
        btnPredictionTest.isEnabled = !isBusy
        btnFirestoreSaveTest.isEnabled = !isBusy
        btnFirestoreReadTest.isEnabled = !isBusy
        btnExportCsv.isEnabled = !isBusy
        btnClearResults.isEnabled = !isBusy
        etRuns.isEnabled = !isBusy
        progressBar.visibility = if (isBusy) View.VISIBLE else View.GONE
    }

    private fun nowString(): String {
        return SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())
    }

    private fun appendResult(operation: String, run: Int, durationMs: Long) {
        val result = PerfResult(
            operation = operation,
            run = run,
            durationMs = durationMs,
            timestamp = nowString()
        )
        results.add(result)

        Log.d("PERF_TEST", "$operation | Run $run | ${durationMs} ms")

        tvResults.text = buildString {
            appendLine("Recorded: $operation | Run $run | ${durationMs} ms")
            appendLine()
            appendLine(buildSummaryText())
        }
    }

    private fun buildSummaryText(): String {
        if (results.isEmpty()) return "No results yet."

        val grouped = results.groupBy { it.operation }
        val builder = StringBuilder()
        builder.appendLine("Summary")
        builder.appendLine("--------------")

        grouped.forEach { (operation, items) ->
            val avg = items.map { it.durationMs }.average()
            val min = items.minOf { it.durationMs }
            val max = items.maxOf { it.durationMs }

            builder.appendLine(operation)
            builder.appendLine("Runs: ${items.size}")
            builder.appendLine("Average: ${"%.2f".format(avg)} ms")
            builder.appendLine("Min: $min ms")
            builder.appendLine("Max: $max ms")
            builder.appendLine()
        }

        return builder.toString()
    }

    private fun runPredictionTests(runs: Int) {
        lifecycleScope.launch {
            setBusy(true)
            try {
                for (i in 1..runs) {
                    val request = PredictionRequest(
                        bedroomsNum = 2,
                        bathroomsNum = 1,
                        locationStd = "Westlands",
                        propertyTypeStd = "apartment",
                        titleClean = "modern apartment westlands"
                    )

                    val start = System.currentTimeMillis()

                    val predictedRent = withContext(Dispatchers.IO) {
                        val response = ApiClient.api.predict(request)
                        if (!response.isSuccessful) {
                            val err = response.errorBody()?.string()
                            throw RuntimeException("Prediction API ${response.code()}: ${err ?: "unknown error"}")
                        }
                        response.body()?.bestValue() ?: 0.0
                    }

                    val end = System.currentTimeMillis()
                    val duration = end - start

                    appendResult("Prediction API", i, duration)
                    Log.d("PERF_TEST", "Predicted rent returned: $predictedRent")
                }

                toast("Prediction test completed")
            } catch (e: Exception) {
                Log.e("PERF_TEST", "Prediction test failed", e)
                toast("Prediction test failed: ${e.message}")
            } finally {
                setBusy(false)
            }
        }
    }

    private fun runFirestoreSaveTests(runs: Int) {
        lifecycleScope.launch {
            setBusy(true)
            try {
                for (i in 1..runs) {
                    val docRef = firestore.collection("performance_tests").document()
                    val docId = docRef.id

                    val sampleData = hashMapOf(
                        "title" to "Performance Test Property $i",
                        "locationName" to "Westlands",
                        "bedrooms" to 2,
                        "bathrooms" to 1,
                        "quotedRent" to 150000.0,
                        "predictedRent" to 163789.22,
                        "rentRatio" to 0.9158,
                        "rentBand" to "FAIR",
                        "createdAt" to nowString(),
                        "testId" to UUID.randomUUID().toString()
                    )

                    val start = System.currentTimeMillis()
                    docRef.set(sampleData).await()
                    val end = System.currentTimeMillis()

                    lastSavedPerfDocId = docId
                    appendResult("Firestore Save", i, end - start)
                }

                toast("Firestore save test completed")
            } catch (e: Exception) {
                Log.e("PERF_TEST", "Firestore save test failed", e)
                toast("Firestore save test failed: ${e.message}")
            } finally {
                setBusy(false)
            }
        }
    }

    private fun runFirestoreReadTests(runs: Int) {
        lifecycleScope.launch {
            setBusy(true)
            try {
                val docId = ensureReadablePerfDocument()

                for (i in 1..runs) {
                    val start = System.currentTimeMillis()
                    firestore.collection("performance_tests")
                        .document(docId)
                        .get()
                        .await()
                    val end = System.currentTimeMillis()

                    appendResult("Firestore Read", i, end - start)
                }

                toast("Firestore read test completed")
            } catch (e: Exception) {
                Log.e("PERF_TEST", "Firestore read test failed", e)
                toast("Firestore read test failed: ${e.message}")
            } finally {
                setBusy(false)
            }
        }
    }

    private suspend fun ensureReadablePerfDocument(): String {
        lastSavedPerfDocId?.let { return it }

        val docRef = firestore.collection("performance_tests").document()
        val docId = docRef.id

        val sampleData = hashMapOf(
            "title" to "Readable Performance Test Property",
            "locationName" to "Kilimani",
            "bedrooms" to 3,
            "bathrooms" to 2,
            "quotedRent" to 180000.0,
            "predictedRent" to 172500.0,
            "rentRatio" to 1.0435,
            "rentBand" to "FAIR",
            "createdAt" to nowString(),
            "testId" to UUID.randomUUID().toString()
        )

        docRef.set(sampleData).await()
        lastSavedPerfDocId = docId
        return docId
    }

    private fun exportResultsToCsv() {
        if (results.isEmpty()) {
            toast("No results to export")
            return
        }

        try {
            val dir = getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS)
                ?: throw RuntimeException("Could not access app documents directory")

            if (!dir.exists()) dir.mkdirs()

            val fileName = "performance_results_${System.currentTimeMillis()}.csv"
            val file = File(dir, fileName)

            FileWriter(file).use { writer ->
                writer.append("Operation,Run,DurationMs,Timestamp\n")
                results.forEach { result ->
                    writer.append("${result.operation},${result.run},${result.durationMs},${result.timestamp}\n")
                }
            }

            val msg = "CSV exported:\n${file.absolutePath}"
            tvResults.text = buildString {
                appendLine(msg)
                appendLine()
                appendLine(buildSummaryText())
            }

            Log.d("PERF_TEST", msg)
            toast("CSV exported successfully")
        } catch (e: Exception) {
            Log.e("PERF_TEST", "CSV export failed", e)
            toast("Export failed: ${e.message}")
        }
    }

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }
}