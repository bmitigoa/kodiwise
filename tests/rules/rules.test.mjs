// Security-rules tests for firestore.rules and storage.rules.
// Run with:  cd tests/rules && npm install && npm test
// (needs Node, Java 21+ and firebase-tools; the emulators are started by `npm test`).
import { test, before, after, beforeEach } from 'node:test';
import { readFileSync } from 'node:fs';
import {
  initializeTestEnvironment,
  assertFails,
  assertSucceeds,
} from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc, updateDoc, deleteDoc, collection, addDoc, getDocs } from 'firebase/firestore';
import { ref, uploadBytes, getBytes, deleteObject, listAll } from 'firebase/storage';

let env;

const PHOTO = (id, file = 'a.jpg') => `properties/${id}/photos/${file}`;
const jpeg = (n = 1000) => new Uint8Array(n).fill(7);
const IMG = { contentType: 'image/jpeg' };

before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'demo-kodiwise',
    firestore: { rules: readFileSync('../../firestore.rules', 'utf8') },
    storage: { rules: readFileSync('../../storage.rules', 'utf8') },
  });
});

after(async () => {
  await env.cleanup();
});

beforeEach(async () => {
  await env.clearFirestore();
  await env.clearStorage();
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, 'users/admin1'), { role: 'admin' });
    await setDoc(doc(db, 'users/owner1'), { role: 'landlord' });
    await setDoc(doc(db, 'users/tenant1'), { role: 'tenant' });
    await setDoc(doc(db, 'users/other1'), { role: 'landlord' });
    for (const [id, status] of [['approved', 'approved'], ['pending', 'pending'], ['deleting', 'deleting']]) {
      await setDoc(doc(db, `properties/${id}`), { ownerId: 'owner1', status, title: id });
      await setDoc(doc(db, `properties/${id}/media/m1`), { storagePath: PHOTO(id), order: 0 });
      await uploadBytes(ref(ctx.storage(), PHOTO(id)), jpeg(), IMG);
    }
  });
});

const as = (uid) => env.authenticatedContext(uid);
const anon = () => env.unauthenticatedContext();

// ---------------------------------------------------------------- storage

test('storage: owner can upload an image to their listing', async () => {
  await assertSucceeds(uploadBytes(ref(as('owner1').storage(), PHOTO('pending', 'new.jpg')), jpeg(), IMG));
});

test('storage: non-image content type is rejected', async () => {
  await assertFails(uploadBytes(ref(as('owner1').storage(), PHOTO('pending', 'x.pdf')), jpeg(), { contentType: 'application/pdf' }));
});

test('storage: file over 2 MB is rejected, 2 MB is allowed', async () => {
  const s = as('owner1').storage();
  await assertFails(uploadBytes(ref(s, PHOTO('pending', 'big.jpg')), jpeg(2 * 1024 * 1024 + 1), IMG));
  await assertSucceeds(uploadBytes(ref(s, PHOTO('pending', 'ok.jpg')), jpeg(2 * 1024 * 1024), IMG));
});

test('storage: someone else cannot upload to a listing they do not own', async () => {
  await assertFails(uploadBytes(ref(as('other1').storage(), PHOTO('pending', 'evil.jpg')), jpeg(), IMG));
  await assertFails(uploadBytes(ref(as('tenant1').storage(), PHOTO('approved', 'evil.jpg')), jpeg(), IMG));
});

test('storage: signed-out user cannot upload or read', async () => {
  await assertFails(uploadBytes(ref(anon().storage(), PHOTO('pending', 'x.jpg')), jpeg(), IMG));
  await assertFails(getBytes(ref(anon().storage(), PHOTO('approved'))));
});

test('storage: upload to a listing that does not exist is denied', async () => {
  await assertFails(uploadBytes(ref(as('owner1').storage(), PHOTO('nope', 'x.jpg')), jpeg(), IMG));
});

test('storage: read is owner, admin, or anyone signed in when approved', async () => {
  await assertSucceeds(getBytes(ref(as('owner1').storage(), PHOTO('pending'))));
  await assertSucceeds(getBytes(ref(as('admin1').storage(), PHOTO('pending'))));
  await assertFails(getBytes(ref(as('tenant1').storage(), PHOTO('pending'))));
  await assertFails(getBytes(ref(as('other1').storage(), PHOTO('pending'))));
  await assertSucceeds(getBytes(ref(as('tenant1').storage(), PHOTO('approved'))));
});

test('storage: a listing being deleted is readable by its owner only', async () => {
  await assertSucceeds(getBytes(ref(as('owner1').storage(), PHOTO('deleting'))));
  await assertFails(getBytes(ref(as('admin1').storage(), PHOTO('deleting'))));
  await assertFails(getBytes(ref(as('tenant1').storage(), PHOTO('deleting'))));
});

test('storage: owner can list and delete photos, others cannot', async () => {
  await assertSucceeds(listAll(ref(as('owner1').storage(), 'properties/pending/photos')));
  await assertFails(deleteObject(ref(as('tenant1').storage(), PHOTO('approved'))));
  await assertFails(deleteObject(ref(as('admin1').storage(), PHOTO('pending'))));
  await assertSucceeds(deleteObject(ref(as('owner1').storage(), PHOTO('pending'))));
  await assertSucceeds(deleteObject(ref(as('owner1').storage(), PHOTO('deleting'))));
});

test('storage: every other path is denied', async () => {
  await assertFails(uploadBytes(ref(as('owner1').storage(), 'misc/x.jpg'), jpeg(), IMG));
  await assertFails(uploadBytes(ref(as('owner1').storage(), 'properties/pending/other/x.jpg'), jpeg(), IMG));
  await assertFails(getBytes(ref(as('owner1').storage(), 'misc/x.jpg')));
});

// -------------------------------------------------------------- firestore

test('firestore: owner can move a listing to deleting, and nothing else', async () => {
  const db = as('owner1').firestore();
  await assertSucceeds(updateDoc(doc(db, 'properties/pending'), { status: 'deleting' }));
  await assertSucceeds(updateDoc(doc(db, 'properties/approved'), { status: 'deleting' }));
  await assertFails(updateDoc(doc(db, 'properties/pending'), { status: 'approved' }));
});

test('firestore: a deleting listing cannot be revived by owner or admin', async () => {
  await assertFails(updateDoc(doc(as('owner1').firestore(), 'properties/deleting'), { status: 'pending' }));
  await assertFails(updateDoc(doc(as('admin1').firestore(), 'properties/deleting'), { status: 'approved' }));
});

test('firestore: a deleting listing is hidden from tenants and admins, visible to the owner', async () => {
  await assertSucceeds(getDoc(doc(as('owner1').firestore(), 'properties/deleting')));
  await assertFails(getDoc(doc(as('admin1').firestore(), 'properties/deleting')));
  await assertFails(getDoc(doc(as('tenant1').firestore(), 'properties/deleting')));
});

test('firestore: owner can finish a delete (media docs, then the listing)', async () => {
  const db = as('owner1').firestore();
  await assertSucceeds(deleteDoc(doc(db, 'properties/deleting/media/m1')));
  await assertSucceeds(deleteDoc(doc(db, 'properties/deleting')));
});

test('firestore: media docs follow the listing (owner, admin, approved)', async () => {
  await assertSucceeds(getDocs(collection(as('tenant1').firestore(), 'properties/approved/media')));
  await assertFails(getDocs(collection(as('tenant1').firestore(), 'properties/pending/media')));
  await assertSucceeds(getDocs(collection(as('admin1').firestore(), 'properties/pending/media')));
  await assertSucceeds(getDocs(collection(as('owner1').firestore(), 'properties/pending/media')));
  await assertFails(getDocs(collection(as('admin1').firestore(), 'properties/deleting/media')));
});

test('firestore: only the owner writes media docs', async () => {
  const entry = { storagePath: PHOTO('pending', 'z.jpg'), order: 1 };
  await assertSucceeds(addDoc(collection(as('owner1').firestore(), 'properties/pending/media'), entry));
  await assertFails(addDoc(collection(as('other1').firestore(), 'properties/pending/media'), entry));
});

test('firestore: owner can set coverPath without changing status', async () => {
  await assertSucceeds(updateDoc(doc(as('owner1').firestore(), 'properties/pending'), { coverPath: PHOTO('pending') }));
});
