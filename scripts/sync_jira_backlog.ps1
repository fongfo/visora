param(
    [ValidateSet('Inspect','Create','Link','Verify')][string]$Action = 'Inspect',
    [string]$PlanPath = 'project/JIRA_BACKLOG.json',
    [string]$ManifestPath = 'project/JIRA_CREATED.json',
    [string]$CredentialFile,
    [int]$MaxTasks = 0
)
$ErrorActionPreference = 'Stop'
if ($CredentialFile) {
    Get-Content -LiteralPath $CredentialFile | ForEach-Object {
        $entry=$_.Trim()
        if ($entry -and -not $entry.StartsWith('#') -and $entry.Contains('=')) {
            $separator=$entry.IndexOf('=')
            [Environment]::SetEnvironmentVariable($entry.Substring(0,$separator).Trim(),$entry.Substring($separator+1).Trim().Trim('"').Trim("'"),'Process')
        }
    }
}
$email = if($env:JIRA_EMAIL){$env:JIRA_EMAIL}else{$env:JIRA_USERNAME}
if (-not $email -or -not $env:JIRA_API_TOKEN) { throw 'Set JIRA_EMAIL and JIRA_API_TOKEN; do not paste credentials into task descriptions.' }
$base = if($env:JIRA_BASE_URL){$env:JIRA_BASE_URL.TrimEnd('/')}elseif($env:JIRA_URL){$env:JIRA_URL.TrimEnd('/')}else{'https://growth-more.atlassian.net'}
if ($base -ne 'https://growth-more.atlassian.net') { throw 'This plan is restricted to the requested Jira site.' }
$headers = @{Authorization=('Basic '+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($email+':'+$env:JIRA_API_TOKEN)));Accept='application/json'}
$plan = Get-Content -Raw -LiteralPath $PlanPath | ConvertFrom-Json
if ($plan.project -ne 'VIS') { throw 'This plan is restricted to VIS.' }
$all = @($plan.epics) + @($plan.tasks)
$mapping = @{}
$issues = @{}

function Invoke-Jira([string]$Method,[string]$Path,$Body=$null) {
    # curl uses the system TLS client; read-only requests may retry.
        # Feed authorization through stdin, never through command-line arguments.
        # Request bodies contain only the public project plan, not credentials.
        $scratch=Join-Path (Get-Location) '.tools/jira'
        [IO.Directory]::CreateDirectory($scratch) | Out-Null
        $bodyPath=Join-Path $scratch ([Guid]::NewGuid().ToString()+'.json')
        if($Method -ne 'GET'){[IO.File]::WriteAllText($bodyPath,($Body | ConvertTo-Json -Depth 40 -Compress),[Text.UTF8Encoding]::new($false))}
        $authConfig='header = "Authorization: '+$headers.Authorization+'"'
        $curlArgs=@('--config','-','--http1.1','--silent','--show-error','--fail-with-body','--connect-timeout','10','--max-time','45','--request',$Method,'--url',($base+$Path),'--header','Content-Type: application/json','--header','Accept: application/json')
        if($Method -ne 'GET'){$curlArgs+=@('--data-binary',('@'+$bodyPath))}
        $attempts=if($Method -eq 'GET'){4}else{1}
        for($attempt=1;$attempt -le $attempts;$attempt++){
            $raw=$authConfig | & curl.exe @curlArgs
            if($LASTEXITCODE -eq 0){break}
            if($attempt -eq $attempts){throw ('Jira request failed or mutation response uncertain: '+($raw -join "`n"))}
            Start-Sleep -Seconds 1
        }
        if($raw){return (($raw -join "`n") | ConvertFrom-Json)}
        return $null
}

function Register-Issue($issue) {
    foreach($label in $issue.fields.labels) {
        if($label.StartsWith('visora-plan-')) {
            $id=$label.Substring('visora-plan-'.Length).ToUpperInvariant()
            if($mapping.ContainsKey($id) -and $mapping[$id] -ne $issue.key){throw "Duplicate plan item $id"}
            $mapping[$id]=$issue.key
            $issues[$issue.key]=$issue
        }
    }
}

function Refresh-Issues {
    $token=$null
    do {
        $path='/rest/api/3/search/jql?jql='+[Uri]::EscapeDataString('project = VIS AND labels = visora-mvp ORDER BY created ASC')+'&maxResults=100&fields=summary,status,issuetype,parent,labels,issuelinks'
        if($token){$path+='&nextPageToken='+[Uri]::EscapeDataString($token)}
        $page=Invoke-Jira GET $path
        foreach($issue in $page.issues){Register-Issue $issue}
        $token=$page.nextPageToken
    } while($token)
    # Direct reads of known keys avoid treating search-index lag as missing issues.
    if(Test-Path -LiteralPath $ManifestPath) {
        $saved=Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
        foreach($item in $saved.items) {
            if(-not $mapping.ContainsKey($item.id)) {
                Register-Issue (Invoke-Jira GET ('/rest/api/3/issue/'+$item.key+'?fields=summary,status,issuetype,parent,labels,issuelinks'))
            }
        }
    }
}

function Save-Manifest {
    $items=@(foreach($item in $all){if($mapping.ContainsKey($item.id)){
        $issue=$issues[$mapping[$item.id]]
        [ordered]@{id=$item.id;key=$issue.key;summary=$issue.fields.summary;type=$issue.fields.issuetype.name;status=$issue.fields.status.name;status_category=$issue.fields.status.statusCategory.key;parent=$issue.fields.parent.key;blocked_by=@($issue.fields.issuelinks | Where-Object {$_.type.name -eq 'Blocks' -and $_.inwardIssue} | ForEach-Object {$_.inwardIssue.key});url=($base+'/browse/'+$issue.key)}
    }})
    [ordered]@{project='VIS';baseline_commit=$plan.baseline_commit;items=$items} | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $ManifestPath -Encoding utf8
}

function Paragraph([string]$text){return @{type='paragraph';content=@(@{type='text';text=$text})}}
function Description($item) {
    $content=[Collections.Generic.List[object]]::new()
    $content.Add((Paragraph ('计划编号：'+$item.id+' | '+$(if($item.priority){'优先级：'+$item.priority}else{'Epic'}))))
    $content.Add((Paragraph ('范围：'+$item.scope)))
    if($item.acceptance){
        $content.Add(@{type='heading';attrs=@{level=3};content=@(@{type='text';text='验收标准'})})
        foreach($criterion in $item.acceptance){$content.Add((Paragraph ('• '+$criterion)))}
        $content.Add((Paragraph ('依赖计划编号：'+$(if($item.deps.Count){$item.deps -join ', '}else{'无'}))))
    } else {
        $content.Add((Paragraph '完成条件：本 Epic 下所有必要任务达到各自验收标准；已完成本地验证不代表真实模型、分布式可靠性或商业上线验收完成。'))
    }
    if($item.done){$content.Add((Paragraph ('已完成证据：development 提交 '+$plan.baseline_commit+'；54 项自动测试通过，详见 project/LOCAL_VALIDATION_REPORT.md。')))}
    foreach($reference in @('https://github.com/fongfo/visora/tree/development','https://github.com/fongfo/visora/blob/development/project/Visora_MVP_Execution_Spec.md','https://github.com/fongfo/visora/blob/development/project/JIRA_BACKLOG.json')){
        $content.Add(@{type='paragraph';content=@(@{type='text';text=$reference;marks=@(@{type='link';attrs=@{href=$reference}})})})
    }
    return @{type='doc';version=1;content=@($content.ToArray())}
}

Refresh-Issues
$project = Invoke-Jira GET '/rest/api/3/project/VIS'
$epicType=($project.issueTypes | Where-Object {$_.name -eq 'Epic'}).id
$taskType=($project.issueTypes | Where-Object {$_.name -eq 'Task'}).id
if(-not $epicType -or -not $taskType){throw 'Required issue types unavailable'}
if($Action -eq 'Inspect') {
    @{project=$project.key;existing=$mapping.Count;epics=$plan.epics.Count;tasks=$plan.tasks.Count;epic_type=$epicType;task_type=$taskType} | ConvertTo-Json
    exit 0
}

if($Action -eq 'Create') {
    foreach($group in @(@{kind='Epic';items=$plan.epics},@{kind='Task';items=$plan.tasks})) {
        $pending=@($group.items | Where-Object {-not $mapping.ContainsKey($_.id)})
        if(-not $pending.Count){continue}
        $updates=@(foreach($item in $pending){
            $phase=if($item.phase){$item.phase}else{($plan.epics | Where-Object {$_.id -eq $item.epic}).phase}
            $labels=@('visora-mvp',('visora-plan-'+$item.id.ToLowerInvariant()),('phase-'+$phase))
            if($item.priority){$labels+=('priority-'+$item.priority.ToLowerInvariant())}
            $fields=@{project=@{key='VIS'};issuetype=@{id=$(if($group.kind -eq 'Epic'){$epicType}else{$taskType})};summary=$item.summary;description=(Description $item);labels=$labels}
            if($item.epic){if(-not $mapping.ContainsKey($item.epic)){throw 'Missing parent Epic'};$fields.parent=@{key=$mapping[$item.epic]}}
            @{fields=$fields}
        })
        Write-Output ('Creating '+$pending.Count+' '+$group.kind+' entries')
        $response=Invoke-Jira POST '/rest/api/3/issue/bulk' @{issueUpdates=$updates}
        foreach($created in $response.issues){
            $issue=Invoke-Jira GET ('/rest/api/3/issue/'+$created.key+'?fields=summary,status,issuetype,parent,labels,issuelinks')
            Register-Issue $issue
            Save-Manifest
            Write-Output ('Created '+$created.key+' '+$issue.fields.summary)
        }
        if($response.errors.Count){$response.errors | ConvertTo-Json -Depth 10;throw 'Bulk create partially failed; reconcile existing labels before resuming.'}
    }
    Save-Manifest
}

if($Action -eq 'Link') {
    $linkTasks=if($MaxTasks -gt 0){@($plan.tasks | Select-Object -First $MaxTasks)}else{@($plan.tasks)}
    foreach($item in $linkTasks) {
        $key=$mapping[$item.id]
        if(-not $key){throw ('Missing '+$item.id)}
        foreach($dependency in $item.deps) {
            $dependencyKey=$mapping[$dependency]
            $existing=@($issues[$key].fields.issuelinks | Where-Object {$_.type.name -eq 'Blocks' -and $_.inwardIssue.key -eq $dependencyKey})
            if(-not $existing.Count) {
                Invoke-Jira POST '/rest/api/3/issueLink' @{type=@{name='Blocks'};inwardIssue=@{key=$dependencyKey};outwardIssue=@{key=$key}} | Out-Null
                Write-Output ($dependencyKey+' blocks '+$key)
            }
        }
        if($item.done -and $issues[$key].fields.status.statusCategory.key -ne 'done') {
            $transitions=Invoke-Jira GET ('/rest/api/3/issue/'+$key+'/transitions')
            $done=@($transitions.transitions | Where-Object {$_.to.statusCategory.key -eq 'done'})
            if(-not $done.Count){throw ('No Done transition for '+$key)}
            Invoke-Jira POST ('/rest/api/3/issue/'+$key+'/transitions') @{transition=@{id=$done[0].id}} | Out-Null
            Write-Output ('Completed '+$key)
        }
    }
}

if($Action -eq 'Verify') {
    $failures=[Collections.Generic.List[string]]::new()
    foreach($item in $all) {
        if(-not $mapping.ContainsKey($item.id)){$failures.Add('Missing '+$item.id);continue}
        $key=$mapping[$item.id]
        $issue=Invoke-Jira GET ('/rest/api/3/issue/'+$key+'?fields=summary,status,issuetype,parent,labels,issuelinks,description')
        $issues[$key]=$issue
        if($issue.fields.summary -ne $item.summary){$failures.Add('Summary mismatch '+$key)}
        $descriptionText=(@($issue.fields.description.content | ForEach-Object {$_.content.text -join ''}) -join "`n")
        foreach($criterion in $item.acceptance){if(-not $descriptionText.Contains($criterion)){$failures.Add('Acceptance criterion missing '+$key)}}
        if($item.priority -and ('priority-'+$item.priority.ToLowerInvariant()) -notin $issue.fields.labels){$failures.Add('Priority label missing '+$key)}
        if($item.epic -and $issue.fields.parent.key -ne $mapping[$item.epic]){$failures.Add('Parent mismatch '+$key)}
        if($item.done -and $issue.fields.status.statusCategory.key -ne 'done'){$failures.Add('Not completed '+$key)}
        foreach($dependency in $item.deps){
            $matching=@($issue.fields.issuelinks | Where-Object {$_.type.name -eq 'Blocks' -and $_.inwardIssue.key -eq $mapping[$dependency]})
            if(-not $matching.Count){$failures.Add('Dependency missing '+$dependency+' -> '+$item.id)}
        }
    }
    Save-Manifest
    @{verified=$all.Count;dependencies=(@($plan.tasks | ForEach-Object {$_.deps})).Count;completed=(@($plan.tasks | Where-Object {$_.done})).Count;failures=@($failures.ToArray())} | ConvertTo-Json -Depth 5
    if($failures.Count){exit 1}
}
