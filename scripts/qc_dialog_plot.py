delete_points = self.qc_dialog.deletion_log
idx = self.view.selectedIndexes()[0]
selected_item = idx.model().itemFromIndex(idx)
if selected_item.rowCount() == 1:
    child = selected_item.child(0, 1)
    if child.text() == "YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM":
        start = delete_points[0][0].strftime("%Y-%m-%d %H:%M")
        end = delete_points[0][1].strftime("%Y-%m-%d %H:%M")
        child.setText(start+","+end)
        continue
    
    