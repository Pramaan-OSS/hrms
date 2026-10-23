// The pinned JavaScript UI package does not ship declarations for these exports.
declare module 'frappe-ui' {
	import type { Component, Plugin } from 'vue'
	export const Button: Component
	export const resourcesPlugin: Plugin
	export function setConfig(key: string, value: unknown): void
	export function frappeRequest(options: { url: string; [key: string]: unknown }): Promise<unknown>
	export function toast(options: {
		title: string
		text: string
		icon?: string
		position?: string
		iconClasses?: string
		timeout?: number
	}): void
}
