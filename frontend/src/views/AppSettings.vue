<template>
	<ion-page>
		<ion-content class="ion-padding">
			<div class="flex flex-col h-screen w-screen">
				<div class="w-full sm:w-96">
					<header
						class="flex flex-row bg-white shadow-sm py-4 px-3 items-center justify-between border-b sticky top-0 z-10"
					>
						<div class="flex flex-row items-center">
							<Button
								variant="ghost"
								class="!pl-0 hover:bg-white"
								@click="router.back()"
							>
								<FeatherIcon name="chevron-left" class="h-5 w-5" />
							</Button>
							<h2 class="text-xl font-semibold text-gray-900">{{ __("Settings") }} </h2>
						</div>
					</header>

					<div class="flex flex-col gap-5 my-4 w-full p-4">
						<div class="flex flex-col bg-white rounded">
							<div
								class="flex flex-row cursor-pointer flex-start p-4 items-center justify-between border-b"
							>
								<router-link
									:to="{ name: 'ChangePassword' }"
									class="flex flex-row items-center justify-between w-full"
								>
									<div class="flex flex-row items-center gap-3 grow">
										<FeatherIcon
											name="lock"
											class="h-5 w-5 text-gray-500"
										/>
										<div class="text-base font-normal text-gray-800">
											{{ __("Change Password") }}
										</div>
									</div>
									<FeatherIcon
										name="chevron-right"
										class="h-5 w-5 text-gray-500"
									/>
								</router-link>
							</div>
						</div>

						<div class="flex flex-col bg-white rounded">
							<div class="flex flex-row items-center justify-between p-4">
								<div class="flex flex-col gap-1">
									<div class="text-base font-normal text-gray-800">
										{{ __("Push Notifications") }}
									</div>
									<div class="text-sm text-gray-500">
										{{ __("Push notifications are not available yet. You still see notifications in the app.") }}
									</div>
								</div>
								<FeatherIcon name="bell-off" class="h-5 w-5 text-gray-400" />
							</div>
						</div>
					</div>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonPage, IonContent } from "@ionic/vue"
import { useRouter } from "vue-router"
import { inject } from "vue"
import { FeatherIcon, Button } from "frappe-ui"

const __ = inject("$translate")
const router = useRouter()
</script>