import dash
from dash import dcc, html, Input, Output, State, ctx, dash_table
import pandas as pd
import sqlite3
import io, os
import base64

app = dash.Dash(__name__)

db_file = "sales.db"
if not os.path.isfile(db_file):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            salesnumber TEXT,
            verkopernummer TEXT,
            price REAL
        )
    """)
    conn.commit()
    conn.close()


def get_next_sales_number():
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(salesnumber) FROM sales")
    max_sales = cursor.fetchone()[0]
    conn.close()
    return str(int(max_sales) + 1) if max_sales else "1"

def sales_number_exists(salesnumber):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sales WHERE salesnumber = ?", (salesnumber,))
    exists = cursor.fetchone()[0] > 0
    conn.close()
    return exists

def generate_excel():
    conn = sqlite3.connect(db_file)
    df = pd.read_sql("SELECT * FROM sales", conn)
    conn.close()

    if df.empty:
        return None
    df = df.rename(columns={'salesnumber': 'Verkoopnummer', 'verkopernummer': 'Verkoper', 'price': 'Prijs'}).drop(columns=['id'])
    totalDF = df[['Verkoper', 'Prijs']].groupby('Verkoper').sum()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Raw Data", index=False)
        totalDF.to_excel(writer, sheet_name='Totalen per verkoper')

    output.seek(0)
    return output.getvalue()

app.layout = html.Div([
    html.H2("Verkoopsysteem kinderkleding"),

    html.Label("Verkoopnummer: "),
    dcc.Input(id="salesnumber", type="text", value=get_next_sales_number(), debounce=True),

    html.Div(id="sales_warning", style={"color": "red", "font-weight": "bold"}),

    html.Br(),

    html.Label("Items"),
    dash_table.DataTable(
        id="sales_table",
        columns=[
            {"name": "Verkoper", "id": "verkopernummer", "editable": True},
            {"name": "Prijs", "id": "price", "editable": True, "type": "numeric"}
        ],
        data=[{"verkopernummer": "", "price": 0.0}],
        editable=True,
        row_deletable=True,
        style_cell = {
            'minWidth': '180px', 'width': '180px', 'maxWidth': '180px',
        },
        fill_width=False
    ),

    html.Button("Item toevoegen", id="add_row", n_clicks=0, style={"margin-top": "10px"}),

    html.Br(), html.Br(),

    html.H4("Totaalbedrag: "),
    html.Div(id="total_amount", style={"font-size": "20px", "font-weight": "bold"}),

    html.Br(),

    html.Button("Verkoop opslaan", id="save_sale", n_clicks=0, style={"background-color": "green", "color": "white"}),

    html.Br(), html.Br(),

    html.Button("Excel downloaden", id="export_excel", n_clicks=0),
    dcc.Download(id="download_excel"),

    html.Br(), html.Br(),

    html.Div(id="status_message", style={"color": "blue", "font-weight": "bold"})
])

# **Unified Callback to Handle Sales Table, Sales Number Check, and Save Sale**
@app.callback(
    Output("status_message", "children"),
    Output("sales_table", "data"),
    Output("salesnumber", "value"),
    Output("sales_warning", "children"),
    Input("save_sale", "n_clicks"),
    Input("salesnumber", "value"),
    Input("add_row", "n_clicks"),
    State("sales_table", "data")
)
def handle_sales(n_save, salesnumber, n_add_row, rows):
    trigger = ctx.triggered_id

    # --- Handle Adding a Row ---
    if trigger == "add_row":
        rows.append({"verkopernummer": "", "price": 0.0})
        return dash.no_update, rows, dash.no_update, dash.no_update

    # --- Handle Sales Number Check ---
    if trigger == "salesnumber":
        exists = sales_number_exists(salesnumber)
        warning_msg = "⚠️ Waarschuwing: Dit verkoopnummer bestaat al! Als je opslaat, overschrijf je de oude verkoop." if exists else ""
        return dash.no_update, dash.no_update, dash.no_update, warning_msg

    # --- Handle Save Sale ---
    if n_save > 0:
        if not salesnumber:
            return "Fout: Verkoopnummer is verplicht!", dash.no_update, dash.no_update, dash.no_update

        exists = sales_number_exists(salesnumber)

        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # Delete old entry if exists (overwrite)
        if exists:
            cursor.execute("DELETE FROM sales WHERE salesnumber = ?", (salesnumber,))

        for row in rows:
            if row["verkopernummer"] and row["price"]:
                cursor.execute("INSERT INTO sales (salesnumber, verkopernummer, price) VALUES (?, ?, ?)",
                               (salesnumber, row["verkopernummer"], row["price"]))

        conn.commit()
        conn.close()

        new_salesnumber = get_next_sales_number()

        # Reset table, update new sales number, and clear warning
        return "Verkoop opgeslagen!", [{"verkopernummer": "", "price": 0.0}], new_salesnumber, ""

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update

# Callback to handle export
@app.callback(
    Output("download_excel", "data"),
    Input("export_excel", "n_clicks"),
    prevent_initial_call=True
)
def export_data(n_clicks):
    excel_data = generate_excel()
    if excel_data:
        from datetime import datetime 
        nu = datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
        return dcc.send_bytes(excel_data, "Verkopen_"+nu+".xlsx")
    return dash.no_update

# Callback to calculate total amount
@app.callback(
    Output("total_amount", "children"),
    Input("sales_table", "data")
)
def update_total_amount(rows):
    total = sum(float(row["price"]) for row in rows if row["price"] not in [None, ""])
    return f"€ {total:.2f}"

if __name__ == '__main__':
    app.run(debug=True, port=8051, host='0.0.0.0')
