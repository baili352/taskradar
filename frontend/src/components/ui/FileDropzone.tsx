import { useRef, useState, type DragEvent } from 'react'
import { UploadCloud } from 'lucide-react'
import { useToast } from './Toast'

const MAX_SIZE_MB = 10
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg']

type FileDropzoneProps = {
  onFiles: (files: File[]) => void
  title?: string
  hint?: string
  multiple?: boolean
  note?: string
}

/** 通用文件拖拽上传区：只做格式与大小校验，上传由调用方处理。 */
export function FileDropzone({
  onFiles,
  title = '拖拽文件到此处，或点击选择文件',
  hint = '支持 PDF / DOCX / TXT / PNG / JPG / JPEG，单个文件不超过 10MB',
  multiple = true,
  note = '文件将上传到本机后端处理，OCR 仅在本机执行',
}: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const { showToast } = useToast()

  const acceptFiles = (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return

    const accepted: File[] = []
    Array.from(fileList).forEach((file) => {
      const dotIndex = file.name.lastIndexOf('.')
      const extension = dotIndex >= 0 ? file.name.slice(dotIndex).toLowerCase() : ''
      if (!ALLOWED_EXTENSIONS.includes(extension)) {
        showToast(`「${file.name}」格式不支持，请上传 PDF / DOCX / TXT / PNG / JPG / JPEG`, 'warning')
        return
      }
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        showToast(`「${file.name}」超过 ${MAX_SIZE_MB}MB，请压缩后重试`, 'warning')
        return
      }
      accepted.push(file)
    })

    if (!multiple && accepted.length > 1) {
      showToast('每次只能分析一个文件，已选择列表中的第一个。', 'info')
    }
    const finalFiles = multiple ? accepted : accepted.slice(0, 1)
    if (finalFiles.length > 0) onFiles(finalFiles)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    acceptFiles(event.dataTransfer.files)
  }

  return (
    <div
      className={`dropzone ${dragging ? 'dragging' : ''}`.trim()}
      role="button"
      tabIndex={0}
      aria-label={title}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          inputRef.current?.click()
        }
      }}
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <span className="dropzone-icon">
        <UploadCloud size={24} />
      </span>
      <strong>{title}</strong>
      <p>{hint}</p>
      <span className="dropzone-note">{note}</span>
      <input
        ref={inputRef}
        type="file"
        className="hidden-input"
        accept={ALLOWED_EXTENSIONS.join(',')}
        multiple={multiple}
        onChange={(event) => acceptFiles(event.target.files)}
      />
    </div>
  )
}
