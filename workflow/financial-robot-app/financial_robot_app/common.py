import logging
import os
from abc import ABC
from typing import List, Optional, Tuple, cast

from dbgpt._private.config import Config
from dbgpt.core.awel import BaseOperator
from dbgpt.datasource.rdbms.base import RDBMSConnector
from dbgpt.datasource.rdbms.conn_sqlite import SQLiteConnector
from dbgpt.rag import Chunk, ChunkParameters
from dbgpt.rag.embedding import EmbeddingFactory, Embeddings
from dbgpt.rag.index.base import IndexStoreBase

logger = logging.getLogger(__name__)


class FinConfigMixin(BaseOperator, ABC):
    _EMBEDDINGS_CACHE_KEY = "__embeddings__"
    _VECTOR_STORE_CACHE_KEY = "__vector_store__"

    _DB_NAME_CACHE_KEY = "__db_name__"
    _SPACE_NAME_CACHE_KEY = "__space_name__"
    _TEMP_DIR_PATH_CACHE_KEY = "__temp_dir_path__"
    _EMBEDDING_MODEL_CACHE_KEY = "__embedding_model__"

    async def get_embeddings(
        self,
        embedding_model: Optional[str] = None,
    ) -> Embeddings:
        embeddings = await self.current_dag_context.get_from_share_data(
            FinConfigMixin._EMBEDDINGS_CACHE_KEY
        )
        if embeddings:
            return embeddings

        if not self.dev_mode:
            from dbgpt.configs.model_config import EMBEDDING_MODEL_CONFIG

            cfg = Config()
            embedding_factory = EmbeddingFactory.get_instance(self.system_app)
            embeddings = embedding_factory.create(
                model_name=EMBEDDING_MODEL_CONFIG[cfg.EMBEDDING_MODEL]
            )
        else:
            from dbgpt.rag.embedding import DefaultEmbeddingFactory

            embeddings = DefaultEmbeddingFactory.default(embedding_model)
        await self.current_dag_context.save_to_share_data(
            FinConfigMixin._EMBEDDINGS_CACHE_KEY, embeddings
        )
        return embeddings

    async def get_reranker(self, reranker_model: Optional[str] = None):
        pass

    async def get_vector_store(
        self, space_name: str, tmp_dir_path: str, embedding_model: Optional[str] = None
    ) -> IndexStoreBase:
        cached_key = f"{FinConfigMixin._VECTOR_STORE_CACHE_KEY}_{space_name}"

        index_store = await self.current_dag_context.get_from_share_data(cached_key)
        if index_store:
            return index_store
        embeddings = await self.get_embeddings(embedding_model)

        if not self.dev_mode:
            # Run this code in DB-GPT
            from dbgpt.configs.model_config import EMBEDDING_MODEL_CONFIG
            from dbgpt.serve.rag.connector import VectorStoreConnector
            from dbgpt.storage.vector_store.base import VectorStoreConfig

            cfg = Config()

            config = VectorStoreConfig(
                name=space_name,
                embedding_fn=embeddings,
            )
            connector = VectorStoreConnector(
                vector_store_type=cfg.VECTOR_STORE_TYPE, vector_store_config=config
            )
            index_store = connector.index_client
        else:
            from dbgpt.storage.vector_store.chroma_store import (
                ChromaStore,
                ChromaVectorConfig,
            )

            index_store = ChromaStore(
                vector_store_config=ChromaVectorConfig(
                    name=space_name,
                    persist_path=os.path.join(tmp_dir_path, space_name),
                    embedding_fn=embeddings,
                ),
            )
        await self.current_dag_context.save_to_share_data(cached_key, index_store)
        return index_store

    async def save_database_profile(
        self, db_name: str, connector: RDBMSConnector, tmp_dir_path: str
    ):
        vector_store_name = db_name + "_profile"

        index_store = await self.get_vector_store(vector_store_name, tmp_dir_path)
        await self.blocking_func_to_async(
            self._save_to_vector_store, connector, index_store
        )

    def _save_to_vector_store(
        self, connector: RDBMSConnector, index_store: IndexStoreBase
    ):
        from dbgpt.rag.assembler.db_schema import DBSchemaAssembler

        db_assembler = DBSchemaAssembler.load_from_connection(
            connector=connector,
            index_store=index_store,
            chunk_parameters=ChunkParameters(chunk_strategy="CHUNK_BY_SIZE"),
        )
        if len(db_assembler.get_chunks()) > 0:
            db_assembler.persist()
        else:
            logger.info("No chunks found in DBSchemaAssembler")

    async def get_db_summary(
        self,
        db_name,
        tmp_dir_path: str,
        query: str,
        top_k: int = 4,
        embedding_model: Optional[str] = None,
    ) -> List[str]:
        from dbgpt.rag.retriever import DBSchemaRetriever

        index_store = await self.get_vector_store(
            db_name + "_profile", tmp_dir_path, embedding_model
        )
        retriever = DBSchemaRetriever(top_k=top_k, index_store=index_store)
        table_docs: List[Chunk] = await retriever.aretrieve(query)
        if (
            isinstance(table_docs, list)
            and table_docs
            and isinstance(table_docs[0], list)
        ):
            # chore: Fix `retriever.aretrieve` return type bug
            table_docs = cast(List[Chunk], table_docs[0])
        return [d.content for d in table_docs]

    async def get_connector(
        self, space: str, db_name: str, tmp_dir_path
    ) -> RDBMSConnector:
        cache_key = f"{space}_{db_name}"
        connector = await self.current_dag_context.get_from_share_data(cache_key)
        if connector:
            return connector
        else:
            tmp_dir_path = tmp_dir_path or "./tmp"
            sqlite_path = os.path.join(tmp_dir_path, space, f"{db_name}.db")
            connector = SQLiteConnector.from_file_path(sqlite_path)
            await self.current_dag_context.save_to_share_data(cache_key, connector)
            return connector

    async def _save_chat_config(
        self,
        db_name: str,
        space_name: str,
        tmp_dir_path: str,
        embedding_model: Optional[str] = None,
    ):
        await self.current_dag_context.save_to_share_data(
            FinConfigMixin._DB_NAME_CACHE_KEY, db_name, overwrite=True
        )
        await self.current_dag_context.save_to_share_data(
            FinConfigMixin._SPACE_NAME_CACHE_KEY, space_name, overwrite=True
        )
        await self.current_dag_context.save_to_share_data(
            FinConfigMixin._TEMP_DIR_PATH_CACHE_KEY, tmp_dir_path, overwrite=True
        )
        if embedding_model:
            await self.current_dag_context.save_to_share_data(
                FinConfigMixin._EMBEDDING_MODEL_CACHE_KEY,
                embedding_model,
                overwrite=True,
            )

    async def _get_chat_config(self) -> Tuple[str, str, str, Optional[str]]:
        db_name = await self.current_dag_context.get_from_share_data(
            FinConfigMixin._DB_NAME_CACHE_KEY
        )
        space_name = await self.current_dag_context.get_from_share_data(
            FinConfigMixin._SPACE_NAME_CACHE_KEY
        )
        tmp_dir_path = await self.current_dag_context.get_from_share_data(
            FinConfigMixin._TEMP_DIR_PATH_CACHE_KEY
        )
        embedding_model = await self.current_dag_context.get_from_share_data(
            FinConfigMixin._EMBEDDING_MODEL_CACHE_KEY
        )

        return db_name, space_name, tmp_dir_path, embedding_model
