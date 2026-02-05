# RoletaV11/main.py

import sys
import os
import tkinter as tk

# Adicionar o diretório raiz ao path para garantir que imports funcionem
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.app_controller import AppController
from ui.main_window import MainWindow

def main():
    print("Iniciando RoletaV11...")
    
    # 1. Inicializar Controller
    controller = AppController()
    
    # 2. Inicializar UI (Root Tkinter)
    root = tk.Tk()
    
    # 3. Construir Janela Principal
    app_ui = MainWindow(root, controller)
    controller.register_ui(app_ui)
    
    # 3. Start App
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Encerrando...")
    finally:
        controller.on_app_close()

if __name__ == "__main__":
    main()
