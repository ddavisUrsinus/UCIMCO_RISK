from thesis_drift.edgar.extract import chunk_text, embed_chunks, extract_text_from_html


SAMPLE_HTML = """<html><head><script>alert('bad')</script><style>p{color:red}</style></head>
<body><h1>Apple Inc.</h1><p>Visible &amp; useful text.</p></body></html>"""


def test_extract_text_from_html_strips_tags_and_noise():
    text = extract_text_from_html(SAMPLE_HTML)
    assert "Apple Inc." in text
    assert "Visible & useful text." in text
    assert "<h1>" not in text
    assert "alert" not in text
    assert "color:red" not in text


def test_chunk_text_count_and_overlap():
    words = [f"w{i}" for i in range(1050)]
    chunks = chunk_text(" ".join(words), chunk_size=500, overlap=50)
    assert len(chunks) == 3
    first = chunks[0].split()
    second = chunks[1].split()
    assert len(first) == 500
    assert second[0] == "w450"
    assert first[450:500] == second[:50]


def test_embed_chunks_returns_384_dim_vectors():
    vectors = embed_chunks(["revenue grew", "margin compressed"])
    assert len(vectors) == 2
    assert all(len(vector) == 384 for vector in vectors)
