"""Routers registrados por `main.py`.

Cada módulo declara o path completo (sem prefixo), então nenhuma URL depende da
ordem de registro — exceto pelo catch-all `/perfil-comportamental/{rest:path}`, que
`main.py` mantém declarado depois de todos os `include_router`.
"""
