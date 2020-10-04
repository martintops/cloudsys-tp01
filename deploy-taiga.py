import googleapiclient.discovery
import argparse
import os
import time

backend_script = r'''
source /home/taiga/.virtualenvs/taiga/bin/activate
cd /home/taiga/taiga-back/
nohup python manage.py runserver 0.0.0.0:8000 > log.txt
'''

frontend_script = r'''
PUBLIC_IP=$(curl -s http://checkip.amazonaws.com/)
sed -i '/"api"/c\    "api": "http://'"$PUBLIC_IP"'/api/v1/",' /home/your_name/taiga-front-dist/dist/conf.json
'''
def create_instance(compute, project, zone, name, image, machine, ip, tags=[], metadata=[]):
    config = {
        'name': name,
        'machineType': "zones/%s/machineTypes/%s" % (zone, machine),
        'disks': [
            {
                'initializeParams': {
                    "sourceImage": image
                },
                "boot": True
            }
        ],
        'tags': {
            "items": tags
        },
        "networkInterfaces": [
            {
                'network': 'global/networks/default',
                'networkIP': ip,
                'accessConfigs': [
                    {
                        'type': 'ONE_TO_ONE_NAT',
                        'name': 'External NAT'
                    }
                ]
            }
        ],
        "metadata": {
            "items": metadata
        }
    }
    return compute.instances().insert(
        project=project,
        zone=zone,
        body=config).execute()

def delete_instance(compute, project, zone, name):
    return compute.instances().delete(
        project=project,
        zone=zone,
        instance=name).execute()

def list_instances(compute, project, zone):
    result = compute.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else None

def wait_for_operation(compute, project, zone, operation):
    print('Waiting for operation to finish...')
    while True:
        result = compute.zoneOperations().get(
            project=project,
            zone=zone,
            operation=operation).execute()

        if result['status'] == 'DONE':
            print("done.")
            if 'error' in result:
                raise Exception(result['error'])
            return result

        time.sleep(1)

def main(mode, project, zone, wait=True):
    compute = googleapiclient.discovery.build('compute', 'v1')

    if(mode == 'list'):
        instances = list_instances(compute, project, zone)

        print('Instances in project %s and zone %s:' % (project, zone))
        for instance in instances:
            print(' - ' + instance['name'])

        return

    print("Creating VM's")
    instance_name = "tp01-database"
    image = "projects/cloudsys-tp01/global/images/tp01-database-image"
    machine = "e2-small"
    ip = "10.128.0.2"
    operation1 = create_instance(compute, project, zone, instance_name, image, machine, ip)

    print("Creating Backend")
    instance_name = "tp01-backend"
    image = "projects/cloudsys-tp01/global/images/tp01-backend-image"
    machine = "e2-medium"
    ip = "10.128.0.3"
    metadata = [{
        "key": "startup-script",
        "value": backend_script
    }]
    operation2 = create_instance(compute, project, zone, instance_name, image, machine, ip, metadata=metadata)

    print("Creating Frontend")
    instance_name = "tp01-frontend"
    image = "projects/cloudsys-tp01/global/images/tp01-frontend-image"
    machine = "e2-small"
    ip = "10.128.0.4"
    metadata = [{
        "key": "startup-script",
        "value": frontend_script
    }]
    tags = ["http-server"]
    operation3 = create_instance(compute, project, zone, instance_name, image, machine, ip, tags, metadata=metadata)

    print("Waiting for VMs to come online")
    wait_for_operation(compute, project, zone, operation1['name'])
    wait_for_operation(compute, project, zone, operation2['name'])
    wait_for_operation(compute, project, zone, operation3['name'])

    instances = list_instances(compute, project, zone)

    print('Instances in project %s and zone %s:' % (project, zone))
    for instance in instances:
        print(' - ' + instance['name'])

    if wait:
        input()

    print("Deleting DB")
    operation1 = delete_instance(compute, project, zone, "tp01-database")
    print("Deleting Backend")
    operation2 = delete_instance(compute, project, zone, "tp01-backend")
    print("Deleting Frontend")
    operation3 = delete_instance(compute, project, zone, "tp01-frontend")
    wait_for_operation(compute, project, zone, operation1['name'])
    wait_for_operation(compute, project, zone, operation2['name'])
    wait_for_operation(compute, project, zone, operation3['name'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mode', help='Wanted mode', default='list')
    parser.add_argument('project_id', help='Your Google Cloud project ID.')
    parser.add_argument(
        '--zone',
        default='us-central1-a',
        help='Compute Engine zone to deploy to.')

    args = parser.parse_args()

    main(args.mode, args.project_id, args.zone)
    