// ตัวค้นแบบเดียวกับ rag/retrieve.py: TF-IDF ตัวอักษร (char_wb 2-4) + BM25 บนคำที่ตัดด้วย Intl.Segmenter
function createEngine(chunks, synonyms) {
  var HYBRID_WEIGHT = 0.5;
  var segmenter = new Intl.Segmenter('th', { granularity: 'word' });

  function indexText(c) { return c.title + '\n' + c.section + '\n' + c.text; }

  function tokenize(text) {
    var out = [];
    for (var s of segmenter.segment(text.toLowerCase())) if (s.isWordLike) out.push(s.segment);
    return out;
  }

  function expandQuery(q) {
    var low = q.toLowerCase();
    var extra = Object.keys(synonyms).filter(function (k) { return low.indexOf(k) !== -1; }).map(function (k) { return synonyms[k]; });
    return { text: [q].concat(extra).join(' '), extra: extra };
  }

  // sklearn TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)) defaults: lowercase, smooth idf, l2 norm
  function charNgrams(text) {
    var grams = [];
    var words = text.toLowerCase().split(/\s+/).filter(Boolean);
    for (var w of words) {
      w = ' ' + w + ' ';
      var chars = Array.from(w);
      for (var n = 2; n <= 4; n++) {
        if (chars.length < n) { grams.push(chars.join('')); continue; }
        for (var i = 0; i + n <= chars.length; i++) grams.push(chars.slice(i, i + n).join(''));
      }
    }
    return grams;
  }

  function counts(list) {
    var m = new Map();
    for (var t of list) m.set(t, (m.get(t) || 0) + 1);
    return m;
  }

  var texts = chunks.map(indexText);
  var N = chunks.length;

  var gramCounts = texts.map(function (t) { return counts(charNgrams(t)); });
  var df = new Map();
  gramCounts.forEach(function (m) { m.forEach(function (_, g) { df.set(g, (df.get(g) || 0) + 1); }); });
  var idf = new Map();
  df.forEach(function (d, g) { idf.set(g, Math.log((1 + N) / (1 + d)) + 1); });

  function tfidfVector(m) {
    var v = new Map(), norm = 0;
    m.forEach(function (c, g) {
      var w = idf.get(g);
      if (w === undefined) return;
      var x = c * w;
      v.set(g, x);
      norm += x * x;
    });
    norm = Math.sqrt(norm) || 1;
    v.forEach(function (x, g) { v.set(g, x / norm); });
    return v;
  }
  var docVecs = gramCounts.map(tfidfVector);

  // rank_bm25.BM25Okapi defaults: k1=1.5, b=0.75, epsilon=0.25
  var K1 = 1.5, B = 0.75, EPS = 0.25;
  var docTokens = texts.map(function (t) { return counts(tokenize(t)); });
  var docLen = texts.map(function (_, i) { var s = 0; docTokens[i].forEach(function (c) { s += c; }); return s; });
  var avgdl = docLen.reduce(function (a, b) { return a + b; }, 0) / N;
  var nd = new Map();
  docTokens.forEach(function (m) { m.forEach(function (_, t) { nd.set(t, (nd.get(t) || 0) + 1); }); });
  var bmIdf = new Map(), idfSum = 0, negatives = [];
  nd.forEach(function (f, t) {
    var v = Math.log(N - f + 0.5) - Math.log(f + 0.5);
    bmIdf.set(t, v);
    idfSum += v;
    if (v < 0) negatives.push(t);
  });
  var eps = EPS * (idfSum / nd.size);
  negatives.forEach(function (t) { bmIdf.set(t, eps); });

  function bm25Scores(qTokens) {
    var scores = new Array(N).fill(0);
    for (var q of qTokens) {
      var w = bmIdf.get(q) || 0;
      if (!w) continue;
      for (var i = 0; i < N; i++) {
        var f = docTokens[i].get(q) || 0;
        scores[i] += w * (f * (K1 + 1) / (f + K1 * (1 - B + B * docLen[i] / avgdl)));
      }
    }
    return scores;
  }

  function tfidfScores(q) {
    var qv = tfidfVector(counts(charNgrams(q)));
    return docVecs.map(function (dv) {
      var s = 0;
      qv.forEach(function (x, g) { var y = dv.get(g); if (y) s += x * y; });
      return s;
    });
  }

  // คำที่ไม่ช่วยบอกหัวข้อ ไม่นับตอนวัดว่าคำถามกับเอกสารมีคำตรงกันแค่ไหน
  var STOP = new Set(['ได้', 'กี่', 'ไหม', 'อย่างไร', 'เท่าไร', 'ต้อง', 'แค่', 'ไหน', 'ที่', 'มี', 'การ', 'ให้', 'ทำ', 'เป็น', 'จะ', 'และ', 'หรือ', 'ของ', 'ใน', 'กับ', 'อะไร', 'บ้าง', 'ยังไง', 'คือ', 'วัน', 'นี้']);
  function queryTerms(text) {
    return Array.from(new Set(tokenize(text))).filter(function (t) { return Array.from(t).length >= 2 && !STOP.has(t); });
  }

  function normalize(a) {
    var top = Math.max.apply(null, a);
    return top > 0 ? a.map(function (x) { return x / top; }) : a.slice();
  }

  // คืนผลเรียงคะแนนจากมากไปน้อย พร้อม cosine ดิบ (relevance) และสัดส่วนคำในคำถามที่พบใน chunk (coverage)
  // สองค่านี้ใช้ตัดสินว่าคำถามอยู่นอกเอกสารหรือไม่
  function search(query, opts) {
    opts = opts || {};
    var k = opts.k || 4;
    var method = opts.method || 'hybrid';
    var includeSuperseded = !!opts.includeSuperseded;
    var expanded = method === 'hybrid' ? expandQuery(query) : { text: query, extra: [] };
    var cos = tfidfScores(expanded.text);
    var scores = cos;
    if (method === 'hybrid') {
      var bm = bm25Scores(tokenize(expanded.text));
      var nc = normalize(cos), nb = normalize(bm);
      scores = nc.map(function (x, i) { return HYBRID_WEIGHT * x + (1 - HYBRID_WEIGHT) * nb[i]; });
    }
    var idx = chunks.map(function (_, i) { return i; });
    idx.sort(function (a, b) { return scores[b] - scores[a] || a - b; });
    if (!includeSuperseded) idx = idx.filter(function (i) { return chunks[i].status === 'active'; });
    var terms = queryTerms(expanded.text);
    return {
      expanded: expanded.extra,
      terms: terms,
      results: idx.slice(0, k).map(function (i) {
        var matched = terms.filter(function (t) { return docTokens[i].has(t); });
        return Object.assign({}, chunks[i], {
          score: scores[i], relevance: cos[i], matched: matched,
          coverage: terms.length ? matched.length / terms.length : 0
        });
      })
    };
  }

  // ฉบับเดิม (superseded) ที่หัวข้อเดียวกับ chunk active นี้ ถ้ามี
  function supersededFor(chunk) {
    return chunks.filter(function (c) {
      return c.status === 'superseded' && c.section === chunk.section && c.title.indexOf(chunk.title) === 0;
    });
  }

  return { search: search, tokenize: tokenize, supersededFor: supersededFor };
}
if (typeof module !== 'undefined') module.exports = { createEngine: createEngine };
