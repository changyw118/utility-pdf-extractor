# --- NEW PIVOT LOGIC FOR EXCEL ---
        # 1. Prepare kWh Pivot Table
        kwh_pivot = df.pivot(index='Month_Num', columns='Year', values='kWh')
        kwh_pivot.index = [df[df['Month_Num'] == m]['Month'].iloc[0] for m in kwh_pivot.index]
        # Add Totals Row
        kwh_pivot.loc['Total kWh per year'] = kwh_pivot.sum()

        # 2. Prepare RM Pivot Table
        rm_pivot = df.pivot(index='Month_Num', columns='Year', values='RM')
        rm_pivot.index = [df[df['Month_Num'] == m]['Month'].iloc[0] for m in rm_pivot.index]
        # Add Totals Row
        rm_pivot.loc['Total Cost (RM) per year'] = rm_pivot.sum()

        # --- EXCEL EXPORT ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Write kWh Table
            kwh_pivot.to_excel(writer, sheet_name='Consumption_kWh')
            # Write RM Table
            rm_pivot.to_excel(writer, sheet_name='Cost_RM')
            
            workbook = writer.book
            num_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
            header_format = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1})
            
            # Apply formatting to both sheets
            for sheet_name in ['Consumption_kWh', 'Cost_RM']:
                worksheet = writer.sheets[sheet_name]
                # Format headers and data cells
                worksheet.set_column(1, 10, 15, num_format)
                worksheet.set_column(0, 0, 20, header_format)
            
        st.download_button(
            label="📥 Download Year-on-Year Excel Report",
            data=output.getvalue(),
            file_name=f"TNB_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
