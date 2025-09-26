import customtkinter as ctk
from tkinter import ttk, messagebox
import pymysql

# ---------------- CONFIGURAÇÃO CUSTOMTKINTER ---------------- #
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# ---------------- USUÁRIO E SENHA ---------------- #
USUARIO = "admin"
SENHA = "1234"

# ---------------- FUNÇÃO DO SISTEMA DE ESTOQUE + PDV ---------------- #
def importar_sistema():
    # ---------------- CONEXÃO COM MYSQL ---------------- #
    con = pymysql.connect(
        host="localhost",
        user="root",
        password="1234",
        database="estoque"
    )
    cur = con.cursor()

    # Criar tabelas se não existirem
    cur.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nome VARCHAR(100) NOT NULL,
        quantidade INT NOT NULL,
        preco_custo FLOAT NOT NULL,
        preco_venda FLOAT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vendas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total FLOAT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS itens_venda (
        id INT AUTO_INCREMENT PRIMARY KEY,
        venda_id INT NOT NULL,
        produto_id INT NOT NULL,
        nome VARCHAR(100),
        quantidade INT NOT NULL,
        preco_unitario FLOAT NOT NULL,
        subtotal FLOAT NOT NULL,
        FOREIGN KEY (venda_id) REFERENCES vendas(id) ON DELETE CASCADE
    );
    """)
    con.commit()

    # ---------- Estado do PDV (carrinho em memória) ----------
    carrinho = []  # cada item: dict {produto_id, nome, quantidade, preco_unitario, subtotal}

    # ---------------- FUNÇÕES DE PDV E ESTOQUE ---------------- #
    def pesquisar_produto():
        termo = entry_pesquisa.get().strip()
        if termo:
            for item in tree.get_children():
                tree.delete(item)
            cur.execute("SELECT id, nome, quantidade, preco_custo, preco_venda FROM produtos WHERE nome LIKE %s",
                        ('%' + termo + '%',))
            resultados = cur.fetchall()
            if resultados:
                for row in resultados:
                    tree.insert("", "end", values=row)
            else:
                messagebox.showinfo("Pesquisa", "Nenhum produto encontrado.")
        else:
            carregar_produtos()

    def carregar_produtos():
        for item in tree.get_children():
            tree.delete(item)
        cur.execute("SELECT id, nome, quantidade, preco_custo, preco_venda FROM produtos")
        for row in cur.fetchall():
            tree.insert("", "end", values=row)
        atualizar_valor_total()  # Atualiza o subtotal do estoque

    def limpar_campos():
        entry_nome.delete(0, ctk.END)
        entry_qtd.delete(0, ctk.END)
        entry_preco_custo.delete(0, ctk.END)
        entry_preco_venda.delete(0, ctk.END)

    # ----------------- FUNÇÕES DO PDV -----------------
    def refresh_carrinho_view():
        # atualiza Treeview do PDV e subtotal
        for it in tree_venda.get_children():
            tree_venda.delete(it)
        subtotal = 0.0
        for it in carrinho:
            tree_venda.insert("", "end", values=(
                it['produto_id'],
                it['nome'],
                it['quantidade'],
                f"{it['preco_unitario']:.2f}",
                f"{it['subtotal']:.2f}"
            ))
            subtotal += it['subtotal']
        label_pdv_subtotal.configure(text=f"Subtotal: R$ {subtotal:.2f}")

    def adicionar_item_pdv(event=None):
        codigo = entry_codigo.get().strip()
        if not codigo:
            messagebox.showwarning("Erro", "Digite o código/ID do produto!")
            return
        try:
            produto_id = int(codigo)
        except ValueError:
            messagebox.showerror("Erro", "Código inválido. Digite um ID numérico.")
            return

        # buscar produto no banco
        cur.execute("SELECT id, nome, preco_venda, quantidade FROM produtos WHERE id=%s", (produto_id,))
        row = cur.fetchone()
        if not row:
            messagebox.showerror("Erro", "Produto não encontrado!")
            return

        _, nome, preco_unit, estoque = row
        try:
            qtd = int(entry_qty.get().strip() or "1")
        except ValueError:
            messagebox.showerror("Erro", "Quantidade inválida.")
            return
        if qtd <= 0:
            messagebox.showerror("Erro", "Quantidade deve ser maior que zero.")
            return
        if qtd > estoque:
            messagebox.showwarning("Estoque", f"Estoque insuficiente. Disponível: {estoque}")
            return

        # se produto já no carrinho, soma quantidade
        for it in carrinho:
            if it['produto_id'] == produto_id:
                it['quantidade'] += qtd
                it['subtotal'] = it['quantidade'] * it['preco_unitario']
                break
        else:
            carrinho.append({
                'produto_id': produto_id,
                'nome': nome,
                'quantidade': qtd,
                'preco_unitario': float(preco_unit),
                'subtotal': qtd * float(preco_unit)
            })

        refresh_carrinho_view()
        entry_codigo.delete(0, ctk.END)
        entry_qty.delete(0, ctk.END)
        entry_qty.insert(0, "1")

    def remover_item_pdv():
        sel = tree_venda.selection()
        if not sel:
            messagebox.showwarning("Erro", "Selecione um item para remover!")
            return
        item = tree_venda.item(sel)
        produto_id = item['values'][0]
        # remove do carrinho
        nonlocal_list = [it for it in carrinho if it['produto_id'] != produto_id]
        carrinho.clear()
        carrinho.extend(nonlocal_list)
        refresh_carrinho_view()

    def limpar_carrinho():
        if not carrinho:
            return
        if messagebox.askyesno("Confirmar", "Limpar todos os itens da venda?"):
            carrinho.clear()
            refresh_carrinho_view()

    def finalizar_venda():
        if not carrinho:
            messagebox.showwarning("Erro", "Carrinho vazio.")
            return
        total = sum(it['subtotal'] for it in carrinho)
        # grava venda
        cur.execute("INSERT INTO vendas (total) VALUES (%s)", (total,))
        venda_id = cur.lastrowid
        # grava itens e atualiza estoque
        for it in carrinho:
            cur.execute(
                "INSERT INTO itens_venda (venda_id, produto_id, nome, quantidade, preco_unitario, subtotal) VALUES (%s, %s, %s, %s, %s, %s)",
                (venda_id, it['produto_id'], it['nome'], it['quantidade'], it['preco_unitario'], it['subtotal'])
            )
            cur.execute("UPDATE produtos SET quantidade = quantidade - %s WHERE id = %s", (it['quantidade'], it['produto_id']))
        con.commit()
        messagebox.showinfo("Venda", f"Venda registrada. ID: {venda_id}  Total: R$ {total:.2f}")
        carrinho.clear()
        refresh_carrinho_view()
        carregar_produtos()

    # ---------------- FUNÇÕES EXISTENTES (CRUD estoque) ---------------- #
    def adicionar_produto():
        nome = entry_nome.get()
        quantidade = entry_qtd.get()
        preco_custo = entry_preco_custo.get()
        preco_venda = entry_preco_venda.get()
        if nome and quantidade and preco_custo and preco_venda:
            cur.execute(
                "INSERT INTO produtos (nome, quantidade, preco_custo, preco_venda) VALUES (%s, %s, %s, %s)",
                (nome, int(quantidade), float(preco_custo), float(preco_venda))
            )
            con.commit()
            carregar_produtos()
            limpar_campos()
        else:
            messagebox.showwarning("Erro", "Preencha todos os campos!")

    def deletar_produto():
        selecionado = tree.selection()
        if not selecionado:
            messagebox.showwarning("Erro", "Selecione um produto para deletar!")
            return
        item = tree.item(selecionado)
        produto_id = item["values"][0]
        cur.execute("DELETE FROM produtos WHERE id=%s", (produto_id,))
        con.commit()
        carregar_produtos()
        limpar_campos()

    def editar_produto():
        selecionado = tree.selection()
        if not selecionado:
            messagebox.showwarning("Erro", "Selecione um produto para editar!")
            return
        item = tree.item(selecionado)
        produto_id = item["values"][0]
        nome = entry_nome.get()
        quantidade = entry_qtd.get()
        preco_custo = entry_preco_custo.get()
        preco_venda = entry_preco_venda.get()
        if nome and quantidade and preco_custo and preco_venda:
            cur.execute(
                "UPDATE produtos SET nome=%s, quantidade=%s, preco_custo=%s, preco_venda=%s WHERE id=%s",
                (nome, int(quantidade), float(preco_custo), float(preco_venda), produto_id)
            )
            con.commit()
            carregar_produtos()
            limpar_campos()
        else:
            messagebox.showwarning("Erro", "Preencha todos os campos!")

    def selecionar_produto(event):
        selecionado = tree.selection()
        if selecionado:
            item = tree.item(selecionado)
            entry_nome.delete(0, ctk.END)
            entry_nome.insert(0, item["values"][1])
            entry_qtd.delete(0, ctk.END)
            entry_qtd.insert(0, item["values"][2])
            entry_preco_custo.delete(0, ctk.END)
            entry_preco_custo.insert(0, item["values"][3])
            entry_preco_venda.delete(0, ctk.END)
            entry_preco_venda.insert(0, item["values"][4])

    def atualizar_relatorio():
        for item in tree_relatorio.get_children():
            tree_relatorio.delete(item)
        cur.execute("SELECT id, nome, quantidade, preco_custo, preco_venda FROM produtos ORDER BY quantidade DESC")
        produtos = cur.fetchall()
        for row in produtos:
            tree_relatorio.insert("", "end", values=row)

    # ------------------ Função para atualizar valor total do estoque ------------------
    def atualizar_valor_total():
        cur.execute("SELECT quantidade, preco_custo FROM produtos")
        total = sum(qtd * preco for qtd, preco in cur.fetchall())
        label_subtotal.configure(text=f"Valor Total Estoque: R$ {total:.2f}")

    # ---------------- INTERFACE ---------------- #
    root = ctk.CTk()
    root.title("Sistema de Estoque / PDV")
    root.geometry("1000x650")

    tab_control = ctk.CTkTabview(root)
    tab_control.pack(expand=True, fill="both", padx=20, pady=12)
    tab_control.add("Venda")
    tab_control.add("Estoque")
    tab_control.add("Relatório")

    # ---------------- ABA VENDA ---------------- #
    aba_venda = tab_control.tab("Venda")
    frame_venda_top = ctk.CTkFrame(aba_venda)
    frame_venda_top.pack(fill="x", padx=12, pady=8)

    ctk.CTkLabel(frame_venda_top, text="Código/ID:").grid(row=0, column=0, padx=6, pady=6, sticky="e")
    entry_codigo = ctk.CTkEntry(frame_venda_top, width=120)
    entry_codigo.grid(row=0, column=1, padx=6, pady=6)
    ctk.CTkLabel(frame_venda_top, text="Qtd:").grid(row=0, column=2, padx=6, pady=6, sticky="e")
    entry_qty = ctk.CTkEntry(frame_venda_top, width=60)
    entry_qty.grid(row=0, column=3, padx=6, pady=6)
    btn_add = ctk.CTkButton(frame_venda_top, text="Adicionar", width=100, command=adicionar_item_pdv)
    btn_add.grid(row=0, column=4, padx=8, pady=6)

    entry_codigo.bind('<Return>', adicionar_item_pdv)

    # Tabela do carrinho (itens da venda)
    frame_venda_table = ctk.CTkFrame(aba_venda)
    frame_venda_table.pack(fill="both", expand=True, padx=12, pady=8)

    cols_venda = ("ID", "Nome", "Qtd", "Unit", "Subtotal")
    tree_venda = ttk.Treeview(frame_venda_table, columns=cols_venda, show="headings", height=10)
    for c in cols_venda:
        tree_venda.heading(c, text=c)
        tree_venda.column(c, width=120)
    tree_venda.pack(side="left", fill="both", expand=True, padx=(0,8), pady=6)

    # Frame lateral com subtotal e botões
    frame_venda_right = ctk.CTkFrame(frame_venda_table)
    frame_venda_right.pack(side="right", fill="y", padx=6, pady=6)

    label_pdv_subtotal = ctk.CTkLabel(frame_venda_right, text="Subtotal: R$ 0.00", font=("Arial", 30))
    label_pdv_subtotal.pack(pady=6)

    ctk.CTkButton(frame_venda_right, text="Remover item", width=140, command=remover_item_pdv).pack(pady=6)
    ctk.CTkButton(frame_venda_right, text="Limpar venda", width=140, command=limpar_carrinho).pack(pady=6)
    ctk.CTkButton(frame_venda_right, text="Finalizar venda", width=140, command=finalizar_venda).pack(pady=20)

    # ---------------- ABA ESTOQUE ---------------- #
    aba_estoque = tab_control.tab("Estoque")
    frame_inputs = ctk.CTkFrame(aba_estoque)
    frame_inputs.pack(padx=20, pady=10, fill="x")

    ctk.CTkLabel(frame_inputs, text="Pesquisar:").grid(row=0, column=0, padx=10, pady=(0,18), sticky="e")
    entry_pesquisa = ctk.CTkEntry(frame_inputs)
    entry_pesquisa.grid(row=0, column=1, padx=10, pady=(0,18))
    ctk.CTkButton(frame_inputs, text="Buscar", command=pesquisar_produto).grid(row=0, column=2, padx=10, pady=(0,18))

    # Frame para o subtotal
    frame_subtotal = ctk.CTkFrame(aba_estoque)
    frame_subtotal.pack(fill="x", padx=20, pady=(10,0))

    label_subtotal = ctk.CTkLabel(frame_subtotal, text="Valor Total Estoque: R$ 0.00", font=("Arial", 25))
    label_subtotal.pack(side="right", padx=10)

    # Inputs do estoque
    ctk.CTkLabel(frame_inputs, text="Nome:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
    entry_nome = ctk.CTkEntry(frame_inputs)
    entry_nome.grid(row=1, column=1, padx=10, pady=5)

    ctk.CTkLabel(frame_inputs, text="Quantidade:").grid(row=2, column=0, padx=10, pady=5, sticky="e")
    entry_qtd = ctk.CTkEntry(frame_inputs)
    entry_qtd.grid(row=2, column=1, padx=10, pady=5)

    ctk.CTkLabel(frame_inputs, text="Preço Custo:").grid(row=3, column=0, padx=10, pady=5, sticky="e")
    entry_preco_custo = ctk.CTkEntry(frame_inputs)
    entry_preco_custo.grid(row=3, column=1, padx=10, pady=5)

    ctk.CTkLabel(frame_inputs, text="Preço Venda:").grid(row=4, column=0, padx=10, pady=5, sticky="e")
    entry_preco_venda = ctk.CTkEntry(frame_inputs)
    entry_preco_venda.grid(row=4, column=1, padx=10, pady=5)

    frame_botoes = ctk.CTkFrame(aba_estoque)
    frame_botoes.pack(padx=20, pady=10, fill="x")
    ctk.CTkButton(frame_botoes, text="Adicionar", fg_color="green", hover_color="#045F02", width=120, command=adicionar_produto).grid(row=0, column=0, padx=10, pady=5)
    ctk.CTkButton(frame_botoes, text="Editar", width=120, command=editar_produto).grid(row=0, column=1, padx=10, pady=5)
    ctk.CTkButton(frame_botoes, text="Deletar", fg_color="red", hover_color="#cc0000", width=120, command=deletar_produto).grid(row=0, column=2, padx=10, pady=5)
    ctk.CTkButton(frame_botoes, text="Limpar Campos", width=120, command=limpar_campos).grid(row=0, column=3, padx=10, pady=5)

    frame_table = ctk.CTkFrame(aba_estoque)
    frame_table.pack(padx=20, pady=10, fill="both", expand=True)

    colunas = ("ID", "Nome", "Quantidade", "Preço Custo", "Preço Venda")
    tree = ttk.Treeview(frame_table, columns=colunas, show="headings")
    for col in colunas:
        tree.heading(col, text=col)
        tree.column(col, width=150)
    tree.pack(fill="both", expand=True)
    tree.bind("<<TreeviewSelect>>", selecionar_produto)

    carregar_produtos()

    # ---------------- ABA RELATÓRIO ---------------- #
    aba_relatorio = tab_control.tab("Relatório")
    frame_relatorio = ctk.CTkFrame(aba_relatorio)
    frame_relatorio.pack(padx=20, pady=10, fill="both", expand=True)

    tree_relatorio = ttk.Treeview(frame_relatorio, columns=colunas, show="headings")
    for col in colunas:
        tree_relatorio.heading(col, text=col)
        tree_relatorio.column(col, width=150)
    tree_relatorio.pack(fill="both", expand=True)

    ctk.CTkButton(aba_relatorio, text="Atualizar Relatório", command=atualizar_relatorio).pack(pady=10)

    atualizar_relatorio()
    root.mainloop()

# ---------------- TELA DE LOGIN ---------------- #
login_window = ctk.CTk()
login_window.geometry("350x200")
login_window.title("Login")

def verificar_login():
    user = entry_usuario.get()
    senha = entry_senha.get()
    if user == USUARIO and senha == SENHA:
        login_window.destroy()
        importar_sistema()
    else:
        messagebox.showerror("Erro", "Usuário ou senha incorretos!")

ctk.CTkLabel(login_window, text="Usuário:").pack(pady=10)
entry_usuario = ctk.CTkEntry(login_window)
entry_usuario.pack(pady=5)

ctk.CTkLabel(login_window, text="Senha:").pack(pady=10)
entry_senha = ctk.CTkEntry(login_window, show="*")
entry_senha.pack(pady=5)

ctk.CTkButton(login_window, text="Entrar", command=verificar_login).pack(pady=20)
login_window.bind('<Return>', lambda event: verificar_login())
login_window.mainloop()