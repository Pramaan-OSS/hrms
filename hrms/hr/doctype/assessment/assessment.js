// Copyright (c) 2026, contributors and license holders. See license.txt

frappe.ui.form.on("Assessment", {
	refresh: function (frm) {
		if (frm.is_new()) return;

		if (!frm.doc.exam_ref) {
			frm.add_custom_button(__("Create Exam"), () => {
				frm.call({ method: "create_on_platform", doc: frm.doc }).then(handle(frm));
			});
		} else {
			if (frm.doc.status !== "Published") {
				frm.add_custom_button(__("Push Pending Questions"), () => {
					frm.call({ method: "push_pending_questions", doc: frm.doc }).then(handle(frm));
				});
				frm.add_custom_button(__("Publish Exam"), () => {
					frappe.confirm(
						__("Publishing freezes the question set. This cannot be undone. Publish now?"),
						() => {
							frm.call({ method: "publish", doc: frm.doc }).then(handle(frm));
						}
					);
				});
			}
			frm.add_custom_button(__("Sync From Platform"), () => {
				frm.call({ method: "sync_from_platform", doc: frm.doc }).then(handle(frm));
			});
			frm.add_custom_button(__("List Invitations"), () => {
				frm.call({ method: "list_invitations", doc: frm.doc }).then((r) => {
					const result = (r && r.message) || {};
					if (result.available === false) {
						frappe.msgprint({ indicator: "orange", message: result.message });
						return;
					}
					const invitations = result.invitations || [];
					const rows = invitations
						.map((row) => `<li>${frappe.utils.escape_html(JSON.stringify(row))}</li>`)
						.join("");
					frappe.msgprint({
						title: __("Invitations"),
						indicator: "blue",
						message: rows ? `<ul>${rows}</ul>` : __("No invitations yet."),
					});
				});
			});
		}
	},
});

const handle = function (frm) {
	return (r) => {
		const result = (r && r.message) || {};
		if (result.available === false) {
			frappe.msgprint({ indicator: "orange", message: result.message });
			return;
		}
		frm.reload_doc();
	};
};
