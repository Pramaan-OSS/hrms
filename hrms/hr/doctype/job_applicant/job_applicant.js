// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// For license information, please see license.txt

// for communication
cur_frm.email_field = "email_id";

frappe.ui.form.on("Job Applicant", {
	setup: function (frm) {
		frm.make_methods = {
			Employee: () =>
				frappe.model.open_mapped_doc({
					method: "hrms.hr.doctype.job_applicant.job_applicant.make_employee",
					frm: frm,
				}),
		};
	},

	refresh: function (frm) {
		frm.set_query("job_title", function () {
			return {
				filters: {
					status: "Open",
				},
			};
		});
		frm.events.show_resume(frm);
		frm.events.create_custom_buttons(frm);
		add_pramaan_buttons(frm);
		frm.events.get_interview_for_dashboard(frm);

		if (!frm.toolbar.page.wrapper.find(".prev-doc").length) {
			frm.toolbar.make_navigation();
		}
	},

	show_resume: function (frm) {
		frm.toggle_display("resume_preview_html", false);
		frm.toggle_display("open_resume_button", false);
		if (frm.doc.resume_link) {
			const src_url = frappe.utils.escape_html(frm.doc.resume_link);
			if (src_url.endsWith(".pdf")) {
				frm.toggle_display("resume_preview_html", true);
				frm.events.show_pdf_preview(frm, src_url);
			} else {
				frm.toggle_display("open_resume_button", true);
			}
		}
	},
	show_pdf_preview: function (frm, src_url) {
		let $preview = $(`<div class="img_preview" style="padding-bottom:12px;">
			<object style="background:#323639;" width="100%">
				<embed
				style="background:#323639;"
				width="100%"
				height="1000px"
				src="${src_url}" type="application/pdf"
				>
			</object>
			</div>`);
		frm.get_field("resume_preview_html").$wrapper.html($preview);
	},
	open_resume_button: function (frm) {
		window.open(frm.doc.resume_link, "_blank", "noopener");
	},
	create_custom_buttons: function (frm) {
		if (!frm.doc.__islocal) {
			if (frm.doc.status == "Open") {
				frm.add_custom_button(__("Shortlist"), () => {
					frm.set_value("status", "Shortlisted");
					frm.save();
					frm.refresh();
				});
				frm.add_custom_button(__("Reject"), () => {
					frm.set_value("status", "Rejected");
					frm.save();
					frm.refresh();
				});
			}
			if (frm.doc.status !== "Rejected" && frm.doc.status !== "Accepted") {
				frm.add_custom_button(__("Schedule Interview"), () => {
					frm.events.show_schedule_interview_dialog(frm);
				});
			}
		}

		if (!frm.doc.__islocal && frm.doc.status == "Accepted") {
			if (frm.doc.__onload && frm.doc.__onload.employee) {
				frm.add_custom_button(__("Show Employee"), function () {
					frappe.set_route("Form", "Employee", frm.doc.__onload.employee);
				});
			} else {
				frm.add_custom_button(__("Create Employee"), function () {
					frm.make_methods.Employee();
				});
			}

			if (frm.doc.__onload && frm.doc.__onload.job_offer) {
				$('[data-doctype="Employee Onboarding"]').find("button").show();
				$('[data-doctype="Job Offer"]').find("button").hide();
				frm.add_custom_button(__("View Job Offer"), function () {
					frappe.set_route("Form", "Job Offer", frm.doc.__onload.job_offer);
				});
			} else {
				$('[data-doctype="Employee Onboarding"]').find("button").hide();
				$('[data-doctype="Job Offer"]').find("button").show();
				frm.add_custom_button(__("Create Job Offer"), function () {
					frappe.route_options = {
						job_applicant: frm.doc.name,
						applicant_name: frm.doc.applicant_name,
						designation: frm.doc.job_opening || frm.doc.designation,
					};
					frappe.new_doc("Job Offer");
				});
			}
		}
	},

	get_interview_for_dashboard: function (frm) {
		if (frm.doc.__islocal) return;

		$("div").remove(".form-dashboard-section.custom");
		frappe.call({
			method: "hrms.hr.doctype.job_applicant.job_applicant.get_interview_details",
			args: {
				job_applicant: frm.doc.name,
			},
			callback: function (r) {
				if (r.message) {
					frm.events.make_dashboard(frm, r.message);
				}
			},
		});
	},

	make_dashboard: function (frm, message) {
		frm.dashboard.add_section(
			frappe.render_template("job_applicant_dashboard", {
				data: message.interviews,
				number_of_stars: message.stars,
			}),
			__("Interview Summary"),
		);
	},

	show_schedule_interview_dialog: function (frm) {
		frappe.model.with_doctype("Interview Detail", () => frm.events.show_schedule_dialog(frm));
	},

	show_schedule_dialog: function (frm) {
		let d = new frappe.ui.Dialog({
			title: __("Schedule Interview"),
			fields: [
				{
					label: __("Interview Type"),
					fieldname: "interview_type",
					fieldtype: "Link",
					options: "Interview Type",
					reqd: 1,
					get_query: () => ({
						filters: frm.doc.designation
							? [["designation", "in", [frm.doc.designation, ""]]]
							: [],
					}),
					onchange() {
						const interview_type = d.get_value("interview_type");
						if (!interview_type) return;
						frappe.call({
							method: "hrms.hr.doctype.interview.interview.get_interviewers",
							args: { interview_type },
							callback(r) {
								d.set_value(
									"interviewers",
									(r.message || []).map((i) => ({ interviewer: i.interviewer })),
								);
							},
						});
					},
				},
				{
					label: __("From Time"),
					fieldname: "from_time",
					fieldtype: "Time",
					reqd: 1,
				},
				{ fieldtype: "Column Break" },
				{
					label: __("Scheduled On"),
					fieldname: "scheduled_on",
					fieldtype: "Date",
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{
					label: __("To Time"),
					fieldname: "to_time",
					fieldtype: "Time",
					reqd: 1,
				},
				{
					fieldtype: "Section Break",
					label: __("Interviewers"),
				},
				{
					fieldname: "interviewers",
					fieldtype: "Table MultiSelect",
					options: "Interview Detail",
				},
			],
			primary_action_label: __("Schedule"),
			primary_action(values) {
				frappe.call({
					method: "hrms.hr.doctype.job_applicant.job_applicant.schedule_interview",
					args: {
						job_applicant: frm.doc.name,
						interview_type: values.interview_type,
						scheduled_on: values.scheduled_on,
						from_time: values.from_time || null,
						to_time: values.to_time || null,
						interviewers: values.interviewers || [],
					},
					callback(r) {
						if (r.message) {
							frappe.show_alert({
								message: __("Interview scheduled successfully"),
								indicator: "green",
							});
							d.hide();
							frm.events.get_interview_for_dashboard(frm);
						}
					},
				});
			},
		});
		d.show();
	},
});

const add_pramaan_buttons = function (frm) {
	if (frm.is_new()) return;

		frm.add_custom_button(__("Read Resume"), () => {
			hrms.pramaan.call("hrms.integrations.pramaan_recruiting.parse_resume", {
				applicant: frm.doc.name,
			}).then((result) => {
				if (!result) return;
				const candidate = result.candidate || {};
				const skills = (candidate.skills || [])
					.map((skill) => frappe.utils.escape_html(String(skill)))
					.join(", ");
				frappe.msgprint({
					title: __("Resume Details"),
					indicator: "blue",
					message: `
						<p><b>${__("Name")}</b>: ${frappe.utils.escape_html(candidate.fullName || "")}</p>
						<p><b>${__("Email")}</b>: ${frappe.utils.escape_html(candidate.email || "")}</p>
						<p><b>${__("Skills")}</b>: ${skills}</p>`,
				});
			});
		}, __("Insights"));

		frm.add_custom_button(__("Screen Resume"), () => {
			hrms.pramaan.review_dialog({
				title: __("Screen This Resume"),
				fields: [
					{
						fieldname: "criteria",
						fieldtype: "Small Text",
						label: __("Job requirements (one per line, 1 to 10)"),
						reqd: 1,
					},
					{
						fieldname: "basis_ground",
						fieldtype: "Select",
						label: __("Candidate consent recorded as"),
						options: "consent\nlegitimate_interest\ncontract",
						default: "consent",
						reqd: 1,
					},
				],
				primary_label: __("Show evidence"),
				on_apply: (values) => {
					const criteria = values.criteria
						.split("\n")
						.map((line) => line.trim())
						.filter(Boolean);
					hrms.pramaan.call(
						"hrms.integrations.pramaan_recruiting.screen_resume",
						{ applicant: frm.doc.name, criteria, basis_ground: values.basis_ground }
					).then((result) => {
						if (!result) return;
						const report = hrms.pramaan.outcome_result(result.report);
						if (!report) return;
						const requirements = (report.requirements || report.rows || report.criteria || [])
							.map((row) => `<li>${frappe.utils.escape_html(JSON.stringify(row))}</li>`)
							.join("");
						frappe.msgprint({
							title: __("Resume Evidence"),
							indicator: "blue",
							message: requirements
								? `<ul>${requirements}</ul><p>${__("A person makes the decision.")}</p>`
								: __("The screen returned no rows. Check the resume and try again."),
						});
					});
				},
			});
		}, __("Insights"));

		const consentField = {
			fieldname: "consent_ref",
			fieldtype: "Data",
			label: __("Consent reference you hold for this candidate"),
			reqd: 1,
		};
		const basisField = {
			fieldname: "basis_ground",
			fieldtype: "Select",
			label: __("Candidate consent recorded as"),
			options: "consent\nlegitimate_interest\ncontract",
			default: "consent",
			reqd: 1,
		};

		frm.add_custom_button(__("Verify Employment"), () => {
			hrms.pramaan.review_dialog({
				title: __("Verify Stated Employment"),
				fields: [
					consentField,
					{
						fieldname: "linkedin_url",
						fieldtype: "Data",
						label: __("Candidate's public profile link"),
						reqd: 1,
					},
					{
						fieldname: "claims",
						fieldtype: "Small Text",
						label: __("Stated employers, one per line (1 to 10)"),
						reqd: 1,
					},
					basisField,
				],
				primary_label: __("Start comparison"),
				on_apply: (values) => {
					const claims = values.claims
						.split("\n")
						.map((line) => line.trim())
						.filter(Boolean)
						.map((employer) => ({ employer }));
					hrms.pramaan.call(
						"hrms.integrations.pramaan_checks.verify_employment",
						{
							job_applicant: frm.doc.name,
							linkedin_url: values.linkedin_url,
							consent_ref: values.consent_ref,
							claims,
							basis_ground: values.basis_ground,
						}
					).then((result) => {
						if (!result) return;
						const report = hrms.pramaan.outcome_result(result.report);
						if (!report) return;
						frappe.msgprint({
							title: __("Employment Comparison"),
							indicator: "blue",
							message: `<pre>${frappe.utils.escape_html(JSON.stringify(report, null, 2))}</pre><p>${__("Findings arrive per claim, for a human reviewer only. No overall pass or fail.")}</p>`,
						});
					});
				},
			});
		}, __("Insights"));

		frm.add_custom_button(__("Background Check"), () => {
			hrms.pramaan.review_dialog({
				title: __("Start Background Check"),
				fields: [
					consentField,
					{ fieldname: "full_name", fieldtype: "Data", label: __("Full name"), reqd: 1 },
					{ fieldname: "father_name", fieldtype: "Data", label: __("Father's name") },
					{ fieldname: "date_of_birth", fieldtype: "Date", label: __("Date of birth") },
					{ fieldname: "address", fieldtype: "Small Text", label: __("Address") },
					{ fieldname: "clearance_number", fieldtype: "Data", label: __("Clearance certificate number") },
					basisField,
				],
				primary_label: __("Start check"),
				on_apply: (values) => {
					hrms.pramaan.call(
						"hrms.integrations.pramaan_checks.start_background_check",
						{
							job_applicant: frm.doc.name,
							consent_ref: values.consent_ref,
							full_name: values.full_name,
							father_name: values.father_name,
							date_of_birth: values.date_of_birth,
							address: values.address,
							clearance_number: values.clearance_number,
							basis_ground: values.basis_ground,
						}
					).then((result) => {
						if (!result) return;
						const report = hrms.pramaan.outcome_result(result.report);
						if (!report) return;
						frappe.msgprint({
							title: __("Background Check"),
							indicator: "blue",
							message: `<pre>${frappe.utils.escape_html(JSON.stringify(report, null, 2))}</pre><p>${__("Counts and certificate facts arrive for a human reviewer. No records found is not a clearance.")}</p>`,
						});
					});
				},
			});
		}, __("Insights"));

		frm.add_custom_button(__("Developer Profile"), () => {
			hrms.pramaan.review_dialog({
				title: __("Look Up Developer Profile"),
				fields: [
					consentField,
					{
						fieldname: "linkedin_url",
						fieldtype: "Data",
						label: __("Candidate's public profile link"),
					},
					{ fieldname: "email", fieldtype: "Data", label: __("Or the candidate's email") },
					basisField,
				],
				primary_label: __("Fetch public facts"),
				on_apply: (values) => {
					hrms.pramaan.call(
						"hrms.integrations.pramaan_checks.fetch_dev_profile",
						{
							job_applicant: frm.doc.name,
							consent_ref: values.consent_ref,
							linkedin_url: values.linkedin_url,
							email: values.email,
							basis_ground: values.basis_ground,
						}
					).then((result) => {
						if (!result) return;
						const report = hrms.pramaan.outcome_result(result.report);
						if (!report) return;
						const accounts = (report.accounts || [])
							.map((row) => `<li>${frappe.utils.escape_html(JSON.stringify(row))}</li>`)
							.join("");
						frappe.msgprint({
							title: __("Developer Profile"),
							indicator: "blue",
							message: accounts
								? `<ul>${accounts}</ul><p>${__("Public facts with sources. No score, no recommendation.")}</p>`
								: __("No public developer accounts were found for the supplied reference."),
						});
					});
				},
			});
		}, __("Insights"));

		frm.add_custom_button(__("Send Assessment"), () => {
			frappe.confirm(
				__("Send the assessment invitation to {0}? A live invitation holds paid credit.", [
					frm.doc.applicant_name || frm.doc.name,
				]),
				() => {
					hrms.pramaan.call("hrms.hr.doctype.assessment.assessment.send_assessment", {
						applicant: frm.doc.name,
					}).then((result) => {
						if (!result) return;
						frm.reload_doc();
						frappe.msgprint({
							title: __("Assessment Sent"),
							indicator: "green",
							message: __("The invitation link was emailed to the candidate."),
						});
					});
				}
			);
		}, __("Assessment"));

		if (frm.doc.assessment_invitation_ref) {
			frm.add_custom_button(__("Refresh Assessment Status"), () => {
				hrms.pramaan.call(
					"hrms.hr.doctype.assessment.assessment.refresh_assessment_status",
					{ applicant: frm.doc.name }
				).then((result) => {
					if (!result) return;
					frm.reload_doc();
					frappe.msgprint({
						title: __("Assessment Status"),
						indicator: "blue",
						message: __("The status was refreshed. Not-ready results stay marked as pending."),
					});
				});
			}, __("Assessment"));

			frm.add_custom_button(__("Withdraw Invitation"), () => {
				frappe.confirm(
					__("Withdraw this unused invitation? Any held credit is released."),
					() => {
						hrms.pramaan.call(
							"hrms.hr.doctype.assessment.assessment.withdraw_invitation",
							{ applicant: frm.doc.name }
						).then((result) => {
							if (!result) return;
							frm.reload_doc();
						});
					}
				);
			}, __("Assessment"));
	}
};
