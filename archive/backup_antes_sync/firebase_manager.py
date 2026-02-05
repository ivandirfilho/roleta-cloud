# firebase_manager.py (versão 2.2 - Import opcional do Firebase)

from queue import Queue
from typing import Optional, Any
from datetime import datetime

import config

# Import opcional do Firebase - não impede execução se não estiver instalado
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    credentials = None
    firestore = None

class FirebaseManager:
    """
    Gerencia a conexão e o listener de dados do Firestore.
    V2.2: Import opcional do Firebase - não impede execução se não estiver instalado.
    """

    def __init__(self, output_queue: Queue):
        self.db: Optional[Any] = None
        self.listener_handle: Optional[Any] = None
        self.output_queue = output_queue
        self.is_connected = False
        self.listener_start_time: Optional[datetime] = None
        if not FIREBASE_AVAILABLE:
            print("Módulo FirebaseManager v2.2 inicializado (Firebase não disponível - modo offline).")
        else:
            print("Módulo FirebaseManager v2.2 inicializado.")

    def initialize(self) -> bool:
        """Tenta inicializar a conexão com o Firebase."""
        if not FIREBASE_AVAILABLE:
            print("FirebaseManager: Firebase não está disponível (módulo não instalado).")
            print("  Instale com: pip install firebase-admin")
            self.is_connected = False
            return False
        
        if firebase_admin._apps:
            self.db = firestore.client()
            self.is_connected = True
            print("FirebaseManager: Conexão com Firebase já estabelecida.")
            return True
        
        try:
            cred = credentials.Certificate(config.CAMINHO_CREDENCIAL)
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            self.is_connected = True
            print("FirebaseManager: Conexão com Firebase estabelecida com sucesso.")
            return True
        except Exception as e:
            print(f"FirebaseManager: Não foi possível conectar ao Firebase: {e}")
            print("  O programa continuará funcionando em modo offline.")
            self.is_connected = False
            return False

    def _on_snapshot(self, doc_snapshot, changes, read_time):
        """Callback executado quando o listener detecta uma ou mais mudanças."""
        for change in changes:
            if change.type.name == 'ADDED':
                nova_jogada = change.document.to_dict()
                print(f"Firestore Listener recebeu: {nova_jogada.get('numero')}")
                self.output_queue.put(nova_jogada)

    def start_listener(self):
        """Inicia o listener para ouvir todas as novas jogadas a partir de agora."""
        if not FIREBASE_AVAILABLE:
            print("Não é possível iniciar o listener: Firebase não está disponível.")
            return
        if not self.is_connected:
            print("Não é possível iniciar o listener: conexão com Firebase não estabelecida.")
            return
        if self.listener_handle:
            print("Listener já está ativo.")
            return

        try:
            # --- LINHA CORRIGIDA ---
            # Captura o timestamp atual da máquina local para o filtro.
            self.listener_start_time = datetime.now()
            
            # Ouve todos os documentos adicionados à coleção 'jogadas_roleta'
            # a partir do momento em que o listener foi iniciado.
            query = self.db.collection("jogadas_roleta").where(
                "timestamp", ">=", self.listener_start_time
            )
            
            self.listener_handle = query.on_snapshot(self._on_snapshot)
            print("Listener do Firestore iniciado com sucesso (Modo Historiador).")
        except Exception as e:
            print(f"Erro ao iniciar o listener do Firestore: {e}")

    def stop_listener(self):
        """Para o listener de dados se ele estiver ativo."""
        if self.listener_handle:
            self.listener_handle.unsubscribe()
            self.listener_handle = None
            print("Listener do Firestore parado.")
