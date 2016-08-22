#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys, re , os
import argparse
import subprocess
import shutil
import time
import tempfile
import stat
import zipfile

from subprocess import Popen, PIPE

os.environ["PYTHONPATH"] = ""

from godockercli.auth import Auth
from godockercli.httputils import HttpUtils
from godockercli.utils import Utils

def create_job_script(command, datasets, dir):

    # parse ::dataset_number in the command
    nb_dataset = 0
    if datasets:
        for dataset in datasets:
           nb_dataset += 1
           command = command.replace("::dataset_"+str(nb_dataset), dir+"/"+os.path.basename(dataset))
           print "command"
           print command
           if not os.path.exists(dir+"/"+os.path.basename(dataset)):
               shutil.copy(dataset, dir+"/"+os.path.basename(dataset))

    script = open("script.sh", "w")
    print "-------- script.sh --------"
    script.write("#!/bin/bash\n")
    print "#!/bin/bash"
    script.write(command)
    print command

def run_job(name, image, external, cpu, ram):
   
    cmd_line = []
    cmd_line.extend(["godjob", "create", "-n", name, "-s", "script.sh", "-i", image, "-c", cpu, "-r", ram])
    if external:
        cmd_line.append("--external_image")
    cmd_line.extend(["-v", "home", "-v", "galaxy"]) #, "-v", "omaha", "-v", "softs", '-v', "db"])
       
    print "\n-- Godocker command line --"
    print ' '.join(cmd_line)

    p = subprocess.Popen(cmd_line, stdout=PIPE, stderr=PIPE) 
    stout, stderr = p.communicate()
    print "STDOUT"
    print stout
    print "STDERR"
    print stderr
    job_id = re.search('Job id is (\d+)', stout).group(1)
    
    return job_id

def get_exit_code(job_id):
    
    Auth.authenticate()

    task = HttpUtils.http_get_request(
        "/api/1.0/task/"+str(job_id),
        Auth.server,
        {'Authorization':'Bearer '+Auth.token},
        Auth.noCert
    )

    job=task.json()

    return Utils.get_execution_status(job['container']['meta']['State']['ExitCode'])

def list_result_files(job_id):

    Auth.authenticate()

    files = HttpUtils.http_get_request("/api/1.0/task/"+str(job_id)+"/files/", Auth.server, {'Authorization':'Bearer '+Auth.token}, Auth.noCert)    

    return files.json()

def parse_dir_and_create_archive(job_id, dir):

    Auth.authenticate()

    files = HttpUtils.http_get_request("/api/1.0/task/"+str(job_id)+"/files/"+dir, Auth.server, {'Authorization':'Bearer '+Auth.token}, Auth.noCert)

    archive = zipfile.ZipFile(os.path.basename(dir)+".zip", 'w')

    for file in files.json():
        if file['type'] == "file":
            download_file = ["godfile", "download", str(job_id), dir+"/"+str(file["name"])]
            p2 = subprocess.Popen(download_file, stdout=PIPE, stderr=PIPE)
            stout, sterr = p2.communicate()

            archive.write(str(file['name']))
        else:
            parse_dir_and_create_archive(job_id, dir+"/"+str(file['name']))

    shutil.move(os.path.basename(dir)+".zip", "godocker_outputs")

def __main__():

    parser = argparse.ArgumentParser()
    parser.add_argument('-n', dest="name")
    parser.add_argument('-d', action='append', dest="datasets")
    parser.add_argument('-c', dest="command")
    parser.add_argument('-i', dest="image")
    parser.add_argument('--external', action='store_true')
    parser.add_argument('--cpu')
    parser.add_argument('--ram')
    parser.add_argument('-o', dest="log")

    options = parser.parse_args()

    os.mkdir('godocker_outputs')

    dir = "/omaha-beach/galaxy"

    script = create_job_script(options.command, options.datasets, dir)

    job_id = run_job(options.name, options.image, options.external, options.cpu, options.ram)

    print "\n----- Godocker job ID -----"
    print str(job_id)

    # wait until the job finished   
    while not Utils.is_finish(job_id):
        time.sleep(10)

    list_files = list_result_files(job_id)

    # download all outputs files in outputs dir
    for file in list_files:
        if file['type'] == 'file':
            download_files = ["godfile", "download", str(job_id), file['name']]
            p2 = subprocess.Popen(download_files, stdout=PIPE, stderr=PIPE)
            stout, sterr = p2.communicate()

            # do not move god.log because it is renamed and cmd.sh is unused
            if file['name'] != "god.log" and file['name'] != "cmd.sh":
                shutil.move(file['name'], "godocker_outputs/")
                   
            if file['name'] == "god.log":
                shutil.move("god_"+str(job_id)+".log", options.log)

            if file['name'] == "god.err":
                with open("godocker_outputs/god.err", "r") as myfile:
                    sys.stderr.write(myfile.read())
                os.remove("godocker_outputs/god.err")
        else:
            parse_dir_and_create_archive(job_id, file['name'])

    # if godocker job is in error, exit in error in galaxy
    if get_exit_code(job_id) == "error":
        sys.exit(1)

    # clean copy files
    #for dataset in datasets:
        #os.remove(dir+"/"+os.path.basename(dataset))

if __name__ == '__main__' :
    __main__()

