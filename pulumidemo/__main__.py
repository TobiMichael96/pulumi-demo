"""An Azure RM Python Pulumi program"""
import base64

import pulumi
from pulumi_azure_native import authorization
from pulumi_azure_native import containerservice
from pulumi_azure_native import managedidentity
from pulumi_azure_native import resources
import pulumi_kubernetes as k8s

config = pulumi.Config()

ssh_public_key = config.require("sshPublicKey")

# Create an Azure Resource Group
resource_group = resources.ResourceGroup('resource_group')

user_assigned_identity = managedidentity.UserAssignedIdentity("userAssignedIdentity", resource_group_name=resource_group.name)

user_assigned_identity_list = pulumi.Output.all(
    authorization.get_client_config(),
    resource_group.name,
    user_assigned_identity.name
).apply(lambda args: {
    "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{}".format(args[0].subscription_id,
                                                                                                               args[1],
                                                                                                               args[2]): {}})

managed_cluster = containerservice.ManagedCluster(
    "managed_cluster",
    resource_group_name=resource_group.name,
    agent_pool_profiles=[containerservice.ManagedClusterAgentPoolProfileArgs(
        count=1,
        enable_node_public_ip=True,
        mode="System",
        name="nodepool",
        os_type="Linux",
        type="VirtualMachineScaleSets",
        vm_size="Standard_B2ms"
    )],
    dns_prefix="dnsprefix",
    enable_rbac=True,
    identity=containerservice.ManagedClusterIdentityArgs(
        type="UserAssigned",
        user_assigned_identities=user_assigned_identity_list
    ),
    linux_profile=containerservice.ContainerServiceLinuxProfileArgs(
        admin_username="azureuser",
        ssh=containerservice.ContainerServiceSshConfigurationArgs(
            public_keys=[containerservice.ContainerServiceSshPublicKeyArgs(
                key_data=ssh_public_key,
            )],
        ),
    ),
    location=resource_group.location,
    network_profile=containerservice.ContainerServiceNetworkProfileArgs(
        load_balancer_profile=containerservice.ManagedClusterLoadBalancerProfileArgs(
            managed_outbound_ips=containerservice.ManagedClusterLoadBalancerProfileManagedOutboundIPsArgs(
                count=1,
            ),
        ),
        load_balancer_sku="standard",
        outbound_type="loadBalancer",
    ),

)

kube_creds = pulumi.Output.all(resource_group.name, managed_cluster.name).apply(
    lambda args: containerservice.list_managed_cluster_user_credentials(resource_group_name=args[0],
                                                                        resource_name=args[1]))

kube_config = kube_creds.kubeconfigs[0].value.apply(lambda enc: base64.b64decode(enc).decode())
custom_provider = k8s.Provider("inflation_provider", kubeconfig=kube_config)

app_name = "nginx"
app_labels = {
    "app": app_name
}

nginx_config = k8s.core.v1.ConfigMap(app_name, metadata=k8s.meta.v1.ObjectMetaArgs(labels=app_labels), data={"index.html": open('index.html').read()}, opts=pulumi.ResourceOptions(provider=custom_provider))

nginx_config_map_name = nginx_config.metadata.apply(lambda args: args.name)

nginx_deployment = k8s.apps.v1.Deployment(
    app_name,
    spec=k8s.apps.v1.DeploymentSpecArgs(
        replicas=1,
        selector=k8s.meta.v1.LabelSelectorArgs(match_labels=app_labels),
        template=k8s.core.v1.PodTemplateSpecArgs(
            metadata=k8s.meta.v1.ObjectMetaArgs(labels=app_labels),
            spec=k8s.core.v1.PodSpecArgs(
                containers=[
                    k8s.core.v1.ContainerArgs(
                        name=app_name,
                        image="nginx:1.15-alpine",
                        volume_mounts=[
                            {
                                "name": "nginx-html",
                                "mountPath": "/usr/share/nginx/html/index.html",
                                "subPath": "index.html",
                            },
                        ],
                    )
                ],
                volumes=[{"name": "nginx-html", "configMap": {"name": nginx_config_map_name}}]
            ),
        ),
    ),
    opts=pulumi.ResourceOptions(provider=custom_provider)
)

service = k8s.core.v1.Service(
    app_name,
    metadata=k8s.meta.v1.ObjectMetaArgs(
        labels=app_labels),
    spec=k8s.core.v1.ServiceSpecArgs(
        selector=app_labels,
        ports=[
            k8s.core.v1.ServicePortArgs(
                port=80,
                target_port=80,
                protocol="TCP"
            )
        ],
        type="LoadBalancer",
    ),
    opts=pulumi.ResourceOptions(provider=custom_provider)
)

pulumi.export("frontend_IP", service.status.apply(lambda s: s.load_balancer.ingress[0].ip))
