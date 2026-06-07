from django.urls import path

from agent_docs.api_v3 import agent_docs_detail_view, agent_docs_index_view

urlpatterns = [
    path('', agent_docs_index_view, name='v3-agent-docs-index'),
    path('<slug:slug>', agent_docs_detail_view, name='v3-agent-docs-detail'),
]
