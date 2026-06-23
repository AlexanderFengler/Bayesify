"""FastAPI transport layer (thin).

Routes, an in-process async job worker, and an SSE progress stream. No engine logic lives here —
the pipeline is ``bayesify.core``. At M1 the engine is the hand-authored stub
(:func:`bayesify.core.stub.build_stub_result`); components a-f replace it incrementally.
"""
