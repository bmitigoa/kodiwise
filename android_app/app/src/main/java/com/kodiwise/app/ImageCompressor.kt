package com.kodiwise.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

/**
 * Prepares a picked photo for upload: applies the EXIF rotation, scales the long
 * side to at most 1600 px and re-encodes as JPEG (~80%, lowered until under about
 * 400 KB). Re-encoding from a Bitmap writes a fresh JPEG with no EXIF block, so
 * GPS position, device model and timestamps are never uploaded.
 */
object ImageCompressor {

    class TooLargeException : Exception("Photo is too large even after compressing")

    suspend fun compress(context: Context, uri: Uri): ByteArray = withContext(Dispatchers.IO) {
        val resolver = context.contentResolver

        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
            ?: throw IllegalStateException("Cannot open photo")
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            throw IllegalStateException("Not a readable image")
        }

        val decodeOpts = BitmapFactory.Options().apply {
            inSampleSize = PhotoRules.sampleSize(bounds.outWidth, bounds.outHeight)
        }
        var bmp = resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, decodeOpts) }
            ?: throw IllegalStateException("Cannot decode photo")

        val orientation = resolver.openInputStream(uri)?.use {
            ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        } ?: ExifInterface.ORIENTATION_NORMAL

        val (w, h) = PhotoRules.scaledSize(bmp.width, bmp.height)
        val matrix = Matrix().apply {
            if (w != bmp.width) postScale(w.toFloat() / bmp.width, h.toFloat() / bmp.height)
            when (orientation) {
                ExifInterface.ORIENTATION_ROTATE_90 -> postRotate(90f)
                ExifInterface.ORIENTATION_ROTATE_180 -> postRotate(180f)
                ExifInterface.ORIENTATION_ROTATE_270 -> postRotate(270f)
                ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> postScale(-1f, 1f)
                ExifInterface.ORIENTATION_FLIP_VERTICAL -> postScale(1f, -1f)
                ExifInterface.ORIENTATION_TRANSPOSE -> { postRotate(90f); postScale(-1f, 1f) }
                ExifInterface.ORIENTATION_TRANSVERSE -> { postRotate(270f); postScale(-1f, 1f) }
            }
        }
        if (!matrix.isIdentity) {
            val out = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, matrix, true)
            if (out !== bmp) bmp.recycle()
            bmp = out
        }

        try {
            var bytes = ByteArray(0)
            for (q in PhotoRules.QUALITY_STEPS) {
                val bos = ByteArrayOutputStream()
                bmp.compress(Bitmap.CompressFormat.JPEG, q, bos)
                bytes = bos.toByteArray()
                if (bytes.size <= PhotoRules.TARGET_BYTES) break
            }
            if (bytes.size > PhotoRules.MAX_FILE_BYTES) throw TooLargeException()
            bytes
        } finally {
            bmp.recycle()
        }
    }
}
